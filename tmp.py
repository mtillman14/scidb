import scifor

pi_assessment = scifor.PathInput("{subject}/{session}/gaitrite.csv", root_folder="root/assessment")
pi_training = scifor.PathInput("{subject}/{session}/gaitrite.csv", root_folder="root/training")

result = scifor.for_each(
    lambda filepath: str(filepath),
    inputs={"filepath": scifor.EachOf(pi_assessment, pi_training)},
    dry_run=True,
    subject=[], session=[],
)