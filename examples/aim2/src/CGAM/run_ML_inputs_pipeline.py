import pandas as pd
import os


# Load raw demographic and gait cycle data
def load_data(demographics_path, matchedCycles_path):
    demographics_df = pd.read_excel(demographics_path)
    matchedCycles_df = pd.read_csv(matchedCycles_path)
    return demographics_df, matchedCycles_df


# Filter matched cycles (FV + SHAM1) and select relevant feature columns
def clean_matched_cycles(df):
    # Filter to only SHAM1 FV gait cycles
    df = df[(df['Speed'] == 'FV') & (df['Intervention'] == 'SHAM1')]

    # Drop symmetry metrics with known missing values
    # drop_cols = [
    #     'StanceDurations_GR_Sym', 'StrideWidths_GR_Sym',
    #     'Single_Support_Time_GR_Sym', 'Double_Support_Time_GR_Sym'
    # ]
    # df = df.drop(columns=drop_cols)

    # Keep metadata columns (first 11)
    base_cols = df.columns[:11].tolist()

    # Filter valid symmetry-based features
    feature_cols = [
        col for col in df.columns[11:]
        # if isinstance(col, str)
        # and 'Sym' in col
        # and col != 'NumSynergies_Sym'
        # and all(x not in col for x in ['RMSE_EMG', 'Lag_EMG', 'Mag_EMG',
        #                                'AUC_EMG', 'RMS_EMG', 'AUC_JointAngles',
        #                                'JointAngles_Max', 'JointAngles_Min'])
    ]
    # Add TenMWT as a feature
    # return df[base_cols + feature_cols + ['TenMWT']]
    return df[base_cols + feature_cols]


# Clean demographic data and engineer BMI, Laterality, etc.
def clean_demographics(df):
    # Drop irrelevant columns
    drop_cols = ['Date of Consent ', 'DOB', 'Session Orthotic Type', 'Chronicity']
    df = df.drop(columns=drop_cols)

    # Days between stroke and SHAM1 session
    df['Days Between'] = (df['Date of SHAM1'] - df['Date of Stroke']).dt.days
    df = df.drop(columns=['Date of Stroke', 'Date of SHAM1'])

    # Encode assistive device and orthotic type as True/False
    df['Community Orthotic Type'] = df['Community Orthotic Type'].notna()
    df['Community Assistive Device'] = df['Community Assistive Device'].notna()

    # Compute BMI and drop original height/weight
    df['BMI'] = ((df['Weight(lbs)'] * 0.453592) / ((df['Height(cm)'] / 100) ** 2)).round(2)
    df = df.drop(columns=['Weight(lbs)', 'Height(cm)'])

    # Determine if paretic and dominant sides match (Laterality)
    df['Laterality'] = df['Dominant side'] == df['Paretic Side']
    df = df.drop(columns=['Dominant side', 'Paretic Side'])

    return df


# # Load muscle slope features (subject-level)
# def load_muscle_slope_features(base_dir, subjects):
#     """
#     Load MuscleSlope features for each subject and return as wide-format DF.
#     """
#     all_subjects = []
#     for subj in subjects:
#         file_path = os.path.join(base_dir, str(subj), "TEPs", "SHAM1", "TEPs_processed_May2025", f"{subj}_SHAM1_PRE_SigmoidMetrics.xlsx")
#         if not os.path.exists(file_path):
#             print(f"Warning: File not found for subject {subj}: {file_path}")
#             continue
#         df = pd.read_excel(file_path, sheet_name="MuscleSlopes")
#         # Pivot to wide format: columns like Muscle_Slope, Muscle_R2, Muscle_X_intercept
#         df_wide = df.pivot_table(index=None, columns="Muscle", values=["Slope", "R2", "X_intercept"]).T
#         df_wide = df_wide.unstack().to_frame().T  # flatten MultiIndex
#         df_wide.columns = [f"{muscle}_{metric}" for metric, muscle in df_wide.columns]
#         df_wide.insert(0, "Subject", subj)
#         all_subjects.append(df_wide)

#     return pd.concat(all_subjects, ignore_index=True)

def load_subject_level_features(base_dir, subjects, demographics_df):
    """
    Load subject-level summary features from 'Slope Averages' and 'X-Intercept Averages' sheets.
    Includes mapping Avg_Left/Right to Paretic/NonParetic using demographics.
    """
    all_subjects = []
    for subj in subjects:
        file_path = os.path.join(base_dir, str(subj), "TEPs", "SHAM1", "TEPs_processed_May2025", f"{subj}_SHAM1_PRE_SigmoidMetrics.xlsx")
        if not os.path.exists(file_path):
            print(f"Warning: File not found for subject {subj}: {file_path}")
            continue
        
        # Determine paretic side for this subject
        paretic_side = demographics_df.loc[demographics_df["Subject"] == subj, "Paretic Side"].values
        if len(paretic_side) == 0:
            print(f"Warning: No paretic side info for subject {subj}. Skipping.")
            continue
        paretic_side = paretic_side[0]

        # --- Load Slope Averages ---
        slope_df = pd.read_excel(file_path, sheet_name="Slope Averages")
        slope_features = {
            "Slope_Ext_All": slope_df["Ext_All"].iloc[0],
            "Slope_Flex_All": slope_df["Flex_All"].iloc[0],
            "Slope_Prox_All": slope_df["Prox_All"].iloc[0],
            "Slope_Dist_All": slope_df["Dist_All"].iloc[0],
            "Lowest_RMT_Slope": slope_df["Lowest_RMT_Slope"].iloc[0],
        }
        # Map Avg_Left/Right to Paretic/NonParetic
        if paretic_side == "Left":
            slope_features["Slope_Paretic_Avg"] = slope_df["Avg_Left"].iloc[0]
            slope_features["Slope_NonParetic_Avg"] = slope_df["Avg_Right"].iloc[0]
        elif paretic_side == "Right":
            slope_features["Slope_Paretic_Avg"] = slope_df["Avg_Right"].iloc[0]
            slope_features["Slope_NonParetic_Avg"] = slope_df["Avg_Left"].iloc[0]
        else:
            raise ValueError(f"Unknown paretic side '{paretic_side}' for subject {subj}")

        # --- Load X-Intercept Averages ---
        xint_df = pd.read_excel(file_path, sheet_name="X-Intercept Averages")
        xint_features = {
            "Xint_Ext_All": xint_df["Ext_All"].iloc[0],
            "Xint_Flex_All": xint_df["Flex_All"].iloc[0],
            "Xint_Prox_All": xint_df["Prox_All"].iloc[0],
            "Xint_Dist_All": xint_df["Dist_All"].iloc[0],
            "Lowest_X_Intercept": xint_df["Lowest_X_Intercept"].iloc[0],
        }
        # Map Avg_Left/Right to Paretic/NonParetic
        if paretic_side == "Left":
            xint_features["Xint_Paretic_Avg"] = xint_df["Avg_Left"].iloc[0]
            xint_features["Xint_NonParetic_Avg"] = xint_df["Avg_Right"].iloc[0]
        elif paretic_side == "Right":
            xint_features["Xint_Paretic_Avg"] = xint_df["Avg_Right"].iloc[0]
            xint_features["Xint_NonParetic_Avg"] = xint_df["Avg_Left"].iloc[0]
        else:
            raise ValueError(f"Unknown paretic side '{paretic_side}' for subject {subj}")

        # Combine all features
        combined_features = {"Subject": subj}
        combined_features.update(slope_features)
        combined_features.update(xint_features)
        all_subjects.append(combined_features)

    return pd.DataFrame(all_subjects)


# Aggregate medians across PRE/POST gait cycles and compute deltas
def compute_pre_post_deltas(df):
    # Drop the "Side" column
    df = df.drop('Side', axis=1)

    # Aggregate by key grouping variables
    group_cols = ['Subject', 'Intervention', 'PrePost', 'Speed', 'Trial']
    agg_features = df.columns[10:]

    agg_dict = {'Cycle': 'count'}
    agg_dict.update({col: 'median' for col in agg_features})

    grouped_df = (
        df.groupby(group_cols)
        .agg(agg_dict)
        .reset_index()
        .rename(columns={'Cycle': 'Cycle_Count'})
    )

    # Separate PRE and POST
    pre_df = grouped_df[grouped_df['PrePost'] == 'PRE'].copy()
    post_df = grouped_df[grouped_df['PrePost'] == 'POST'].copy()

    # Ensure trials are integer type
    pre_df['Trial'] = pre_df['Trial'].astype(int)
    post_df['Trial'] = post_df['Trial'].astype(int)

    # Extract feature columns
    feature_cols = pre_df.columns[pre_df.columns.get_loc('Cycle_Count'):]

    # Generate paired comparisons
    rows = []
    for subj in pre_df['Subject'].unique():
        pre_sub = pre_df[pre_df['Subject'] == subj]
        post_sub = post_df[post_df['Subject'] == subj]
        for _, pre_row in pre_sub.iterrows():
            for _, post_row in post_sub.iterrows():
                row = {
                    'Subject': subj,
                    'Trial': pre_row['Trial'],
                    'Trial_Diff': int(f"{pre_row['Trial']}{post_row['Trial']}")
                }
                for col in feature_cols:
                    row[col] = pre_row[col]
                    row[f"{col}_Diff"] = pre_row[col] - post_row[col]
                rows.append(row)

    return grouped_df, pd.DataFrame(rows)


# Create filtered subsets of the final data for modeling
def split_dataframes(final_df):
    final_df = final_df.sort_values(by=['Subject', 'Trial_Diff'])

    # Create masks
    subjectMask = final_df.columns.str.contains(r"Subject|Trial")
    gaitMask    = final_df.columns.str.contains(r"Cycle|Sym|TenMWT")
    mepMask     = final_df.columns.str.contains(r"TEP|RMT|Excitability|Slope|R2|X_intercept")

    # All combined data
    AllData_df = final_df.copy()
    Gait_df    = final_df.loc[:, subjectMask | gaitMask]

    # Pre-only (no *Diff columns, one row per trial)
    PreOnlyData_df = (
        final_df
        .loc[:, ~final_df.columns.str.contains(r"Diff")]
        .drop_duplicates(subset=["Subject", "Trial"])
    )

    # Reapply masks
    subjectMask_pre = PreOnlyData_df.columns.str.contains(r"Subject|Trial")
    gaitMask_pre    = PreOnlyData_df.columns.str.contains(r"Cycle|Sym|TenMWT")
    mepMask_pre     = PreOnlyData_df.columns.str.contains(r"TEP|RMT|Excitability|Slope|R2|X_intercept")

    # Split into logical sets
    Pre_Gait_df = PreOnlyData_df.loc[:, subjectMask_pre | gaitMask_pre]
    MEPs_df     = PreOnlyData_df.loc[:, subjectMask_pre | mepMask_pre]
    Demo_df     = PreOnlyData_df.loc[:, subjectMask_pre | ~(gaitMask_pre | mepMask_pre)]

    # Merge Demographics + MEPs (drop duplicates first)
    id_cols = Demo_df.columns.intersection(MEPs_df.columns)
    Demo_MEPs_df = pd.concat(
        [Demo_df, MEPs_df.drop(columns=id_cols)],
        axis=1
    )

    return {
        "AllData": AllData_df,
        "Gait": Gait_df,
        "PreOnlyData": PreOnlyData_df,
        "Pre_Gait": Pre_Gait_df,
        "MEPs": MEPs_df,
        "Demo": Demo_df,
        "Demo_MEPs": Demo_MEPs_df
    }


# Wrapper pipeline to run everything
def run_preprocessing_pipeline(demographics_path, matchedCycles_path, export_dir=None):
    # Load raw data
    demographics_df, matchedCycles_df = load_data(demographics_path, matchedCycles_path)

    # Filter + clean both datasets
    filtered_cycles = clean_matched_cycles(matchedCycles_df)
    cleaned_demo = clean_demographics(demographics_df)

    # Aggregate median PRE/POST and calculate deltas
    median_df, expanded_df = compute_pre_post_deltas(filtered_cycles)

    # # Load and merge muscle slope features
    # muscle_slope_features = load_muscle_slope_features(
    #     base_dir=r"Y:\Spinal Stim_Stroke R01\AIM 1\Subject Data",
    #     subjects=demographics_df['Subject'].unique()
    # )
    # median_df = pd.merge(median_df, muscle_slope_features, on="Subject", how="left")
    # expanded_df = pd.merge(expanded_df, muscle_slope_features, on="Subject", how="left")
    
    # Load and merge subject-level Slope and X-Intercept features
    subject_features = load_subject_level_features(
    base_dir=r"Y:\Spinal Stim_Stroke R01\AIM 1\Subject Data",
    subjects=demographics_df['Subject'].unique(),
    demographics_df=demographics_df
)
    median_df = pd.merge(median_df, subject_features, on="Subject", how="left")
    expanded_df = pd.merge(expanded_df, subject_features, on="Subject", how="left")


    # Merge demographics with median/diff tables
    merged_df = pd.merge(median_df, cleaned_demo, on='Subject', how='inner')
    final_df = pd.merge(expanded_df, cleaned_demo, on='Subject', how='left')

    # Drop any duplicate columns (keeping the first occurrence)
    final_df = final_df.loc[:, ~final_df.columns.duplicated()]

    # Enforce correct column order
    subject_trial_cols = ['Subject', 'Trial']
    trial_diff_col = ['Trial_Diff']
    base_and_feature_cols = [
        col for col in expanded_df.columns
        if col not in subject_trial_cols + trial_diff_col and not col.endswith('_Diff')
    ]
    other_diff_cols = [
        col for col in expanded_df.columns
        if col.endswith('_Diff') and col != 'Trial_Diff'
    ]
    demo_cols = [col for col in cleaned_demo.columns if col != 'Subject']

    # Final desired column order
    final_col_order = subject_trial_cols + trial_diff_col + base_and_feature_cols + other_diff_cols + demo_cols
    final_df = final_df[[col for col in final_col_order if col in final_df.columns]]


    # Split into modeling sets
    split_dfs = split_dataframes(final_df)

    # Optional export
    if export_dir:
        for name, df in split_dfs.items():
            filename = f"Model_Input_AllFeat_{name}.csv"
            df.to_csv(os.path.join(export_dir, filename), index=False)
            print(f"Wrote {filename}  —  {df.shape[0]} rows × {df.shape[1]} cols")

    return split_dfs
