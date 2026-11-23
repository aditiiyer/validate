# Glossary

AI model
: A trained neural network that contours structures on a scan, such as CT_HN_SMIT for
  head-and-neck organs. VALIDATE installs and runs these through pyCERR.

Analysis folder
: The **Output** folder of an analysis, holding its settings, logs and results.

Derived structure
: A structure VALIDATE makes from AI contours, for example by combining or subtracting
  them. See {doc}`reference/models`.

Dose metric
: A number summarising the dose to a structure, such as its mean dose (`meanDose`).

DVH
: Dose-volume histogram: the fraction of a structure's volume receiving at least each dose.
  Dose metrics are read from it.

Dosimetric model
: A model that predicts a toxicity from dose metrics, and sometimes clinical predictors.

Fractionation correction
: Converting a dose given in one fractionation to an equivalent dose in the model's
  reference fractionation, so the model can be applied to differently fractionated plans.

NTCP
: Normal tissue complication probability: the predicted probability, from 0 to 1, that a
  patient develops the toxicity.

Predictor
: An input to a dosimetric model: a dose metric or a clinical factor such as concurrent
  chemotherapy.

SCRR
: Stem-cell rich region of the parotid glands.
