# Extending VALIDATE

## Add a derived structure

A derived structure is made from AI outputs (or from other structures) by a recipe in
`seg/structures.py`. Once registered, **Derive** is offered for it on the **Model** tab, and
the Segment tab lists the AI model it needs.

1. Write the recipe. It takes the patient's `planC` (with the AI outputs already added under
   their label names) and the scan index, adds the new structure, and returns its index and
   the updated `planC`:

   ```python
   def deriveSubmandibularGlands(planC, scanNum):
       outStructName = 'Submandibular glands'
       planC = cerrStr.structUnion(['Submandibular_L', 'Submandibular_R'], planC,
                                   unionStructName=outStructName)
       structNum = len(planC.structure) - 1
       return structNum, planC
   ```

   The input names are the AI model's output labels (from its `models.yaml`). pyCERR's
   `cerr.dataclasses.structure` has the union, intersection and difference operations.

2. Register it at the end of the file, under the structure's name **as it appears in the
   dosimetric model**:

   ```python
   STRUCTURE_REGISTRY["Submandibular glands"] = StructureDerivation(
       aiModelNum=7, aiModelName="CT_HN_SMIT", deriveFn=deriveSubmandibularGlands, type='AI')
   ```

   - `type='AI'`: made from an AI model's outputs; give the model's number and name.
   - `type='classic'`: made by a non-AI method (`aiModelNum=None`). Classic recipes are run
     first, since AI recipes may use them (as Parotids-SCRR uses SCRR).

3. Add a test in `tests/test_structures.py`.
4. Add the structure to the table in {doc}`../user_guide/reference/models`.

## Add an AI model

AI models come from pyCERR's `cerr.ai_models`: VALIDATE installs and runs any model in its
model list, by number and name. To use a new one:

1. Add it to pyCERR's AI model list (in pyCERR), with a `models.yaml` giving its output
   labels.
2. Reference it from the recipes that use its outputs (see above). The Segment tab then
   lists it for every dosimetric model that needs one of those structures.

## Add a dosimetric model

Dosimetric models are JSON files in pyCERR (`cerr/roe/model_parameters/`). The **Model** list
shows every model pyCERR lists, so a model added to pyCERR appears automatically.

The JSON gives, under `parameters`:

- `structures`: each structure, its dose metric(s) and their weights;
- one entry per other parameter. Those with `"val": null` are clinical predictors that the
  user supplies in the predictors CSV, with their codes in `desc`;
- `fractionCorrect` and `correctionType` (`frxsize` or `frxnum`) if the dose needs
  correcting for fractionation.

To try a model that isn't in pyCERR yet, put its JSON file anywhere and set `model.name` and
`model.file` in `analysis.yaml`. Opening that analysis folder in the GUI adds the model to the
**Model** list.

If the model needs structures with no recipe, users choose **Use existing** for them. Add a
recipe (above) to let them be derived.

## Add a GUI screenshot

User Guide screenshots are generated, not taken by hand. See
{ref}`regenerating-screenshots`.
