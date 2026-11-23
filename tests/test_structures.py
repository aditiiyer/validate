"""Structure derivations (seg/structures.py): each derived structure comes out under
the name the dosimetric model expects (its STRUCTURE_REGISTRY key), from the
structures CT_HN_SMIT outputs.

pyCERR's structure operations are replaced with stand-ins that check their input
structures exist and add the output by name, so no image data is needed.
"""

from types import SimpleNamespace

import pytest

from validate.seg import structures

# CT_HN_SMIT's output structures
SMIT_STRUCTURES = ["Brainstem", "Parotid_L", "Parotid_R", "Submandibular_L", "Submandibular_R",
                   "Mandible", "Oral_Cavity", "SpinalCord", "Pterygoid_L", "Pterygoid_R",
                   "Masseter_L", "Masseter_R", "Thyroid", "Larynx", "BrachialPlexus_L", "BrachialPlexus_R"]


def _struct(name):
    return SimpleNamespace(structureName=name)


def _requireStructures(planC, names):
    available = [s.structureName for s in planC.structure]
    missing = [name for name in names if name not in available]
    if missing:
        raise ValueError(f"Missing input structure(s): {missing}")


@pytest.fixture
def planC(monkeypatch):
    """A planC holding CT_HN_SMIT's outputs, with pyCERR's structure operations stubbed."""
    def structUnion(names, planC, unionStructName):
        _requireStructures(planC, names)
        planC.structure.append(_struct(unionStructName))
        return planC

    def structDiff(name1, name2, planC, diffStructName):
        _requireStructures(planC, [name1, name2])
        planC.structure.append(_struct(diffStructName))
        return planC

    def runSegModel(modelName, planC, scanNum, paramDict):
        assert set(paramDict["structNameDict"]) == {"left_parotid", "right_parotid", "left_masseter",
                                                    "right_masseter", "mandible"}
        _requireStructures(planC, list(paramDict["structNameDict"].values()))
        planC.structure += [_struct("leftSCRR"), _struct("rightSCRR")]
        return None, None, planC

    monkeypatch.setattr(structures.cerrStr, "structUnion", structUnion)
    monkeypatch.setattr(structures.cerrStr, "structDiff", structDiff)
    monkeypatch.setattr(structures.segModels, "run", runSegModel)
    return SimpleNamespace(structure=[_struct(name) for name in SMIT_STRUCTURES])


# Structures a recipe uses that are themselves derived first (classic recipes run first)
PREREQUISITES = {"Parotids-SCRR": ["SCRR"]}


def _derive(planC, structName):
    for prerequisite in PREREQUISITES.get(structName, []):
        _, planC = _derive(planC, prerequisite)
    return structures.getDerivation(structName).deriveFn(planC, 0)


@pytest.mark.parametrize("structName", list(structures.STRUCTURE_REGISTRY))
def test_derivedStructureHasModelName(planC, structName):
    structNum, planC = _derive(planC, structName)
    assert planC.structure[structNum].structureName == structName
