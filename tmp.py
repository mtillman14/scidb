from pathlib import Path

import pandas as pd
import numpy as np

import scifor
from csvstats.anova import anova2way
from csvstats.ttest import ttest_dep

# %% CONSTANTS
RENDER_PLOT = False

SCHEMA = [
    "subject",
    "intervention",
    "speed",
    "prepost",    
    "trial",
    "cycle",
]

NON_NUMERIC_COLS = [
    "Frequency",
    "Is_Stim",      
    "SessionOrder",
    "Intensity",
    "Side",
]

scifor.set_schema(SCHEMA)

# %% PATHS
symmetry_df_path = Path(f"results/from_matlab/Overground_EMG_Kinematics/MergedTablesAffectedUnaffected/matchedCycles_withCGAM.csv")
anova2way_root_save = Path("results/stats/ANOVA results 2way/between_interventions_change_score_with_sham2/matchedCycles")
ttest_root_save = Path("results/stats/ttest_results_change_score")

# Load the symmetry data
df = pd.read_csv(symmetry_df_path)
# Rename columns to match the schema
df.rename(columns={"Subject": "subject", "Intervention": "intervention", "PrePost": "prepost", "Speed": "speed", "Trial": "trial", "Cycle": "cycle"}, inplace=True)
df = df[df["intervention"]!="SHAM1"] # Make sure SHAM1 is removed

# %% Make the CSV files for the stats analyses
# 2-way ANOVA: The mean of each pre/post, speed & intervention
means_df = scifor.for_each(lambda x: np.nanmean(x, axis=0),
    inputs={"x": scifor.ColumnSelection(df, columns=[], excl_columns=NON_NUMERIC_COLS, iterate=True)}, 
    subject=[], intervention=[], prepost=[], speed=[]
)

# The change in mean between pre and post for each subject, intervention, and speed
deltas_df = scifor.for_each(lambda df, col_name: np.mean(df.loc[df["prepost"]=="PRE", col_name].values) - np.mean(df.loc[df["prepost"]=="POST", col_name].values),
    inputs={"df": scifor.ColumnSelection(means_df, columns=[], iterate=True), "col_name": scifor.ColName},
    subject=[], intervention=[], speed=[],
    as_table=True
)

no_sham_deltas_df = deltas_df[deltas_df["intervention"]!="SHAM2"]
sham_deltas_df = deltas_df[deltas_df["intervention"]=="SHAM2"]

# Compute the best and worst change scores for each subject, and speed
best_mag_df = scifor.for_each(lambda x: np.max(x, axis=0),
    inputs={"x": scifor.ColumnSelection(no_sham_deltas_df, columns=[], iterate=True)},
    subject=[], speed=[]
)
best_intervention_df = scifor.for_each(lambda df, col_name: df.loc[df[col_name].idxmax(), "intervention"],
    inputs={
        "df": scifor.ColumnSelection(no_sham_deltas_df, columns=[], iterate=True),
        "col_name": scifor.ColName,
    },
    subject=[], speed=[],
    as_table=True,
)


worst_mag_df = scifor.for_each(lambda x: np.min(x, axis=0),
    inputs={"x": scifor.ColumnSelection(no_sham_deltas_df, columns=[], iterate=True)},
    subject=[], speed=[]
)
worst_intervention_df = scifor.for_each(lambda df, col_name: df.loc[df[col_name].idxmin(), "intervention"],
    inputs={
        "df": scifor.ColumnSelection(no_sham_deltas_df, columns=[], iterate=True),
        "col_name": scifor.ColName,
    },
    subject=[], speed=[],
    as_table=True,
)

best_deltas_df = scifor.for_each(lambda df, best_stim, col_name: df.loc[df["intervention"] == best_stim[col_name].iloc[0], col_name].iloc[0],
    inputs={
        "df": scifor.ColumnSelection(no_sham_deltas_df, columns=[], iterate=True),
        "best_stim": scifor.ColumnSelection(best_intervention_df, columns=[], iterate=True),
        "col_name": scifor.ColName
    },
    as_table=True,
    subject=[], speed=[]
)

worst_deltas_df = scifor.for_each(lambda df, worst_stim, col_name: df.loc[df["intervention"] == worst_stim[col_name].iloc[0], col_name].iloc[0],
    inputs={
        "df": scifor.ColumnSelection(no_sham_deltas_df, columns=[], iterate=True),
        "worst_stim": scifor.ColumnSelection(worst_intervention_df, columns=[], iterate=True),
        "col_name": scifor.ColName
    },
    as_table=True,
    subject=[], speed=[]
)

sham_deltas_df["intervention"] = "SHAM"
best_deltas_df["intervention"] = "STIM"
worst_deltas_df["intervention"] = "STIM"
best_vs_sham_df = pd.concat([best_deltas_df, sham_deltas_df], ignore_index=True)
worst_vs_sham_df = pd.concat([worst_deltas_df, sham_deltas_df], ignore_index=True)

# %% Save the CSV files
best_df_mag_save_path = Path("results/stats/ChangeScore_ttest_CSVs/change_score_matchedCycles_mag_best.csv")
best_df_int_save_path = Path("results/stats/ChangeScore_ttest_CSVs/change_score_matchedCycles_int_best.csv")
worst_df_mag_save_path = Path("results/stats/ChangeScore_ttest_CSVs/change_score_matchedCycles_mag_worst.csv")
worst_df_int_save_path = Path("results/stats/ChangeScore_ttest_CSVs/change_score_matchedCycles_int_worst.csv")

means_df_save_path = Path("results/stats/ChangeScore_CSVs/change_score_matchedCycles_means_for_2wayANOVA.csv")
deltas_df_save_path = Path("results/stats/ChangeScore_CSVs/change_score_matchedCycles_deltas.csv")

deltas_best_vs_sham_df_save_path = Path("results/stats/ChangeScore_ttest_CSVs/change_score_matchedCycles_deltas_best_vs_sham.csv")
deltas_worst_vs_sham_df_save_path = Path("results/stats/ChangeScore_ttest_CSVs/change_score_matchedCycles_deltas_worst_vs_sham.csv")

best_mag_df.to_csv(best_df_mag_save_path, index=False)
best_intervention_df.to_csv(best_df_int_save_path, index=False)
worst_mag_df.to_csv(worst_df_mag_save_path, index=False)
worst_intervention_df.to_csv(worst_df_int_save_path, index=False)
means_df.to_csv(means_df_save_path, index=False)
deltas_df.to_csv(deltas_df_save_path, index=False)

best_vs_sham_df.to_csv(deltas_best_vs_sham_df_save_path, index=False)
worst_vs_sham_df.to_csv(deltas_worst_vs_sham_df_save_path, index=False)


# %% Run the stats analyses
anova2way_root_save.mkdir(parents=True, exist_ok=True)
ttest_root_save.mkdir(parents=True, exist_ok=True)

anova2way_results = scifor.for_each(anova2way,
    inputs={
        "data": scifor.ColumnSelection(means_df, columns=[], iterate=True),
        "group_column1": "intervention",
        "group_column2": "prepost",
        "data_column": scifor.ColName,
        "repeated_measures_column": "subject",
        "filename": scifor.PathOutput(anova2way_root_save.joinpath("{ColName}_anova2way.pdf")),
        "render_plot": RENDER_PLOT,                                        
    },
    as_table=True,
    speed=[]
)

ttest_best_results = scifor.for_each(ttest_dep,
    inputs={
        "data": scifor.ColumnSelection(best_vs_sham_df, columns=[], iterate=True),
        "group_column": "intervention",
        "data_column": scifor.ColName,
        "repeated_measures_column": "subject",
        "filename": scifor.PathOutput(ttest_root_save.joinpath("{ColName}_best_vs_sham.csv")),
        "render_plot": RENDER_PLOT,
    },
    as_table=True,
    speed=[]
)

ttest_worst_results = scifor.for_each(ttest_dep,
    inputs={
        "data": scifor.ColumnSelection(worst_vs_sham_df, columns=[], iterate=True),
        "group_column": "intervention",
        "data_column": scifor.ColName,
        "repeated_measures_column": "subject",
        "filename": scifor.PathOutput(ttest_root_save.joinpath("{ColName}_worst_vs_sham.csv")),
        "render_plot": RENDER_PLOT,
    },
    as_table=True,
    speed=[]
)

