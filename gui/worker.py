"""Background thread running the full Run pipeline (auto-segmentation, if
any structures need it, then NTCP computation) without blocking the GUI.
"""

from PyQt5.QtCore import QThread, pyqtSignal

from validate.src.apply_model import applyModelToCohort
from validate.src.logging import TaskLog
from validate.src.autoseg_pipeline import runAutoSegmentationForCohort


class RunPipelineWorker(QThread):
    stage = pyqtSignal(str)                # current-stage label text
    progress = pyqtSignal(int, int, str)   # done, total, patientId (NTCP stage only)
    finishedOk = pyqtSignal(object, str)   # resultsDf, taskLogPath
    failed = pyqtSignal(str, str)          # message, taskLogPath

    def __init__(self, cohortDir, modelName, structNameMap, autosegStructNames,
                installBaseDir=None, overwrite=False, patientInfoCsv=None, parent=None):
        super().__init__(parent)
        self.cohortDir = cohortDir
        self.modelName = modelName
        self.structNameMap = structNameMap
        self.autosegStructNames = autosegStructNames
        self.installBaseDir = installBaseDir
        self.overwrite = overwrite
        self.patientInfoCsv = patientInfoCsv

    def run(self):
        taskLog = TaskLog(self.cohortDir)
        try:
            if self.autosegStructNames:
                self.stage.emit("Running auto-segmentation...")
                taskLog.stage("Auto-segmentation")
                autosegResults = runAutoSegmentationForCohort(
                    self.cohortDir, self.autosegStructNames, self.installBaseDir,
                    self.patientInfoCsv, taskLog,
                    progressCallback=lambda msg: self.stage.emit(msg),
                    overwrite=self.overwrite)

                autosegErrors = []
                autosegSucceeded = 0
                for patientId, structStatuses in autosegResults.items():
                    for structName, status in structStatuses.items():
                        if status.startswith("error"):
                            autosegErrors.append((patientId, structName, status))
                        else:
                            autosegSucceeded += 1
                taskLog.summary(autosegSucceeded, len(autosegErrors))
                for patientId, structName, status in autosegErrors:
                    taskLog.error(patientId, f"{structName}: {status}")

                # Auto-segmented structures are exported under their own
                # required name, so NTCP computation can "Match" on it
                # directly -- per-patient failures surface naturally there
                # (structure missing -> DVH lookup error) without special
                # handling here.
                for structName in self.autosegStructNames:
                    self.structNameMap[structName] = structName

            self.stage.emit("Computing NTCP...")
            taskLog.stage("NTCP computation")
            resultsDf = applyModelToCohort(
                self.cohortDir, self.modelName, patientInfoCsv=self.patientInfoCsv,
                structNameMap=self.structNameMap,
                progressCallback=lambda done, total, pid:
                    self.progress.emit(done, total, pid))

            ntcpErrors = resultsDf[resultsDf["status"] == "error"]
            taskLog.summary(len(resultsDf) - len(ntcpErrors), len(ntcpErrors))
            for _, row in ntcpErrors.iterrows():
                taskLog.error(row["patient_id"], row["message"])

            self.stage.emit("Logging task report...")
            taskLog.stage("Done")
            taskLog.close()
            self.finishedOk.emit(resultsDf, str(taskLog.path))
        except Exception as exc:
            taskLog.error("(run)", str(exc))
            taskLog.close()
            self.failed.emit(str(exc), str(taskLog.path))
