"""Registry mapping a required structure to the auto-segmentation method.
Contains functions to:
- Transform raw AI outputs to the structures required to run a dosimetric model including
operations such as union, intersection, diff etc.
- Identify the structures required by a dosimetric model, and apply a user-supplied name mapping.

Structures with derivation recipes (STRUCTURE_REGISTRY, end of this file): Oral cavity, Submandibular glands,
SCRR, Parotids-SCRR
"""

import json
import warnings
from dataclasses import dataclass
from typing import Callable

import cerr.dataclasses.structure as cerrStr
from cerr.segmentation import models as segModels
from cerr.roe import dosimetric_models as doseModels

@dataclass
class StructureDerivation:
    deriveFn: Callable # deriveFn(planC) -> (structNum, planC): post-process auto-seg outputs,
                       # returns index of new structure and updated planC.
    aiModelNum: int = None
    aiModelName: str = None
    type: str = 'AI' # 'AI' or 'classic'

STRUCTURE_REGISTRY: dict[str, StructureDerivation] = {}

def getDerivation(structName):
    """Return the StructureDerivation for structName, or None if no
    derivation is registered yet.
    """
    return STRUCTURE_REGISTRY.get(structName)


def listReqdAISegModels(modelFile):
    """Names of the AI models whose outputs a dosimetric model's structures are
    derived from (by their registered recipes), in the order the structures are listed."""
    aiModels = []
    for structName in getRequiredStructures(modelFile):
        derivation = getDerivation(structName)
        if derivation and derivation.aiModelName and derivation.aiModelName not in aiModels:
            aiModels.append(derivation.aiModelName)
    return aiModels


def getRequiredAiModels(structNames):
    """Resolve the AI models needed to auto-segment structNames.

    Returns:
        (models, missing) where models is {aiModelNum: aiModelName} for the
        distinct AI models needed, and missing is the list of structNames
        with no registered derivation.
    """
    models = {}
    missing = []
    for name in structNames:
        derivation = STRUCTURE_REGISTRY.get(name)
        if derivation is None:
            missing.append(name)
        else:
            models[derivation.aiModelNum] = derivation.aiModelName
    return models, missing


def loadModelJSON(modelFile):
    """Load a model's parameter dict.
    modelFile: a built-in model name, a path to a parameter JSON file, or a dict (returned as-is).
    """
    if isinstance(modelFile, dict):
        return modelFile
    if isinstance(modelFile, str) and ".json" not in modelFile:
        modelFile = doseModels.mapModelToFile(modelFile)
    with open(modelFile, "r") as f:
        return json.load(f)


def getRequiredStructures(modelFile):
    """Return the structure names a model requires or an empty list if none.
    """
    model = loadModelJSON(modelFile)
    modelStructs = model.get("parameters", {}).get("structures")

    if modelStructs is None:
        return []
    if isinstance(modelStructs, dict):
        return list(modelStructs.keys())
    if isinstance(modelStructs, str):
        return [modelStructs]
    if isinstance(modelStructs, list):
        return list(modelStructs)
    raise ValueError(
        f"Unrecognized 'structures' entry in model parameters: {modelStructs!r}")


def applyStructureNameMap(modelFile, structNameMap):
    """Return a copy of the model dict with required structures renamed to
     dataset-specific versions.

    Args:
        modelFile: model name, JSON path, or dict (see loadModelDict).
        structNameMap (dict): {modelStructName: datasetStructName}. A
            missing or blank mapping for a structure leaves its name
            unchanged.

    Returns:
        dict: a copy of the model dict with parameters.structures renamed.
    """
    model = loadModelJSON(modelFile)
    if not structNameMap:
        return model

    modelStructs = model.get("parameters", {}).get("structures")

    def _rename(name):
        return structNameMap.get(name) or name

    if isinstance(modelStructs, dict):
        renamed = {_rename(name): params for name, params in modelStructs.items()}
    elif isinstance(modelStructs, str):
        renamed = _rename(modelStructs)
    elif isinstance(modelStructs, list):
        renamed = [_rename(name) for name in modelStructs]
    else:
        return model

    newModel = dict(model)
    newModel["parameters"] = dict(model["parameters"])
    newModel["parameters"]["structures"] = renamed
    return newModel


#--------------------------------------------------------------
# Derive structures required by dosimetric models
#--------------------------------------------------------------
def _getIndex(planC, strName):
    strList = [s.structureName for s in planC.structure]
    matches = cerrStr.getMatchingIndex(strName, strList, 'exact')
    if not matches:
        raise ValueError(f"Structure '{strName}' not found.")
    return matches[0]


def deriveOralCavity(planC, scanNum):
    structNum = _getIndex(planC, 'Oral_Cavity')
    planC.structure[structNum].structureName = 'Oral cavity'
    return structNum, planC


def deriveSubmandibularGlands(planC, scanNum):
    outStructName = 'Submandibular glands'
    planC = cerrStr.structUnion(['Submandibular_L','Submandibular_R'], planC, unionStructName=outStructName)
    structNum = len(planC.structure)-1
    return structNum, planC


def deriveSCRR(planC, scanNum):
    modelName = 'SCRR'
    paramDict = {'structNameDict': {'parotid': ['Parotid_L', 'Parotid_R'],
                                    'masseter': ['Masseter_L', 'Masseter_R'],
                                    'mandible': ['Mandible']}}
    __, __, planC = segModels.run(modelName, planC, scanNum, paramDict)
    planC = cerrStr.structUnion(['leftSCRR', 'rightSCRR'], planC, unionStructName=modelName)
    structNum = len(planC.structure) - 1
    return structNum, planC


def deriveParotidsSCRR(planC, scanNum):
    outStructName = 'Parotids-SCRR'
    planC = cerrStr.structUnion(['Parotid_L', 'Parotid_R'], planC, unionStructName='Parotids')
    planC = cerrStr.structDiff('Parotids','SCRR', planC, diffStructName=outStructName)
    structNum = len(planC.structure) - 1
    return structNum, planC


#---------------------------------------------------------------
# Build registry of structures required across dosimetric models
#---------------------------------------------------------------
STRUCTURE_REGISTRY["Oral cavity"] = StructureDerivation(aiModelNum=7, aiModelName="CT_HN_SMIT", deriveFn=deriveOralCavity, type='AI')
STRUCTURE_REGISTRY["Submandibular glands"] = StructureDerivation(aiModelNum=7, aiModelName="CT_HN_SMIT", deriveFn=deriveSubmandibularGlands, type='AI')
STRUCTURE_REGISTRY["SCRR"] = StructureDerivation(aiModelNum=None, aiModelName=None, deriveFn=deriveSCRR, type='classic')
STRUCTURE_REGISTRY["Parotids-SCRR"] = StructureDerivation(aiModelNum=7, aiModelName="CT_HN_SMIT", deriveFn=deriveParotidsSCRR, type='AI')