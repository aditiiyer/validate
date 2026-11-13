"""The AI model install record and its weights hash (seg/model_registry.py)."""

import os

import pytest

from cerr.ai_models import install_utils

from validate.seg import model_registry

MODEL = "CT_HeadAndNeck_OARs"
MODEL_NUM = 3


@pytest.fixture
def install(tmp_path, monkeypatch):
    """An empty install folder for MODEL, with the install record kept in tmp_path."""
    monkeypatch.setattr(model_registry, "REGISTRY_PATH", tmp_path / "ai_model_installs.yaml")
    installDir = tmp_path / "models"
    modelName, repo, _ = install_utils.getModel(MODEL_NUM)
    repoPath = installDir / repo
    (repoPath / "weights").mkdir(parents=True)
    (repoPath / "models.yaml").write_text(f"models:\n  {modelName}:\n    description: test\n")
    return installDir, repoPath / "weights", modelName


def test_weightsHashedAtInstall(install):
    installDir, weightsDir, modelName = install
    (weightsDir / f"{modelName}.pt").write_bytes(b"weights v1")
    model_registry.recordInstall(MODEL_NUM, modelName, installDir)

    entry = model_registry.readRegistry()[str(MODEL_NUM)]
    assert entry["weightsSha256"]
    assert entry["weightsStamp"]["size"] == len(b"weights v1")
    assert model_registry.getWeightsHash(MODEL_NUM) == entry["weightsSha256"]


def test_unchangedWeightsNotHashedAgain(install, monkeypatch):
    installDir, weightsDir, modelName = install
    (weightsDir / f"{modelName}.pt").write_bytes(b"weights v1")
    model_registry.recordInstall(MODEL_NUM, modelName, installDir)
    stored = model_registry.getWeightsHash(MODEL_NUM)

    monkeypatch.setattr(model_registry, "_hashWeights", lambda path: pytest.fail("weights hashed again"))
    assert model_registry.getWeightsHash(MODEL_NUM) == stored


def test_changedWeightsHashedAgain(install):
    installDir, weightsDir, modelName = install
    weightsFile = weightsDir / f"{modelName}.pt"
    weightsFile.write_bytes(b"weights v1")
    model_registry.recordInstall(MODEL_NUM, modelName, installDir)
    oldHash = model_registry.getWeightsHash(MODEL_NUM)

    weightsFile.write_bytes(b"weights v2, longer")
    newHash = model_registry.getWeightsHash(MODEL_NUM)
    assert newHash != oldHash
    assert model_registry.readRegistry()[str(MODEL_NUM)]["weightsSha256"] == newHash


def test_sameSizeChangeDetectedByModificationTime(install):
    installDir, weightsDir, modelName = install
    weightsFile = weightsDir / f"{modelName}.pt"
    weightsFile.write_bytes(b"weights v1")
    model_registry.recordInstall(MODEL_NUM, modelName, installDir)
    oldHash = model_registry.getWeightsHash(MODEL_NUM)

    weightsFile.write_bytes(b"weights v2")
    later = os.stat(weightsFile).st_mtime + 10
    os.utime(weightsFile, (later, later))
    assert model_registry.getWeightsHash(MODEL_NUM) != oldHash


def test_weightsFolderHashed(install):
    installDir, weightsDir, modelName = install
    folder = weightsDir / modelName
    (folder / "fold0").mkdir(parents=True)
    (folder / "fold0" / "model.pt").write_bytes(b"a")
    (folder / "plans.json").write_bytes(b"b")
    model_registry.recordInstall(MODEL_NUM, modelName, installDir)
    firstHash = model_registry.getWeightsHash(MODEL_NUM)

    (folder / "plans.json").write_bytes(b"changed")
    assert model_registry.getWeightsHash(MODEL_NUM) != firstHash


def test_weightsNotInstalled(install):
    installDir, _, modelName = install
    model_registry.recordInstall(MODEL_NUM, modelName, installDir)
    entry = model_registry.readRegistry()[str(MODEL_NUM)]
    assert entry["weightsSha256"] is None
    assert model_registry.getWeightsHash(MODEL_NUM) is None


def test_weightsAddedAfterInstallAreHashed(install):
    installDir, weightsDir, modelName = install
    model_registry.recordInstall(MODEL_NUM, modelName, installDir)
    (weightsDir / f"{modelName}.pt").write_bytes(b"weights v1")
    assert model_registry.getWeightsHash(MODEL_NUM) is not None


def test_modelNotRecorded(install):
    assert model_registry.getWeightsHash(MODEL_NUM) is None


def test_installStatusUsesPyCERRLayout(install):
    installDir, weightsDir, modelName = install
    model_registry.recordInstall(MODEL_NUM, modelName, installDir)
    assert model_registry.getInstallInfo(MODEL_NUM)[0] is False      # no weights yet
    (weightsDir / f"{modelName}.pt").write_bytes(b"weights v1")
    assert model_registry.getInstallInfo(MODEL_NUM)[0] is True


def test_useInstallRecordsNewFolder(install):
    installDir, weightsDir, modelName = install
    (weightsDir / f"{modelName}.pt").write_bytes(b"weights v1")
    model_registry.useInstall(MODEL_NUM, modelName, installDir)
    entry = model_registry.readRegistry()[str(MODEL_NUM)]
    assert entry["installDir"] == str(installDir)
    assert entry["weightsSha256"]


def test_useInstallKeepsSameFolder(install, monkeypatch):
    installDir, weightsDir, modelName = install
    (weightsDir / f"{modelName}.pt").write_bytes(b"weights v1")
    model_registry.recordInstall(MODEL_NUM, modelName, installDir)
    monkeypatch.setattr(model_registry, "recordInstall", lambda *args: pytest.fail("recorded again"))
    model_registry.useInstall(MODEL_NUM, modelName, installDir)


def test_useInstallRefusesFolderWithoutWeights(install):
    installDir, _, modelName = install
    with pytest.raises(RuntimeError, match=f"{modelName} is not installed in"):
        model_registry.useInstall(MODEL_NUM, modelName, installDir)


def test_installStatus(install):
    installDir, weightsDir, modelName = install
    assert model_registry.installStatus(MODEL_NUM, None) == "not installed"
    assert model_registry.installStatus(MODEL_NUM, installDir.parent / "elsewhere") == "not installed"
    assert model_registry.installStatus(MODEL_NUM, installDir) == "no weights"
    (weightsDir / f"{modelName}.pt").write_bytes(b"weights v1")
    assert model_registry.installStatus(MODEL_NUM, installDir) == "installed"
