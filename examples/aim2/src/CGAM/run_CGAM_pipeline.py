import pandas as pd
import numpy as np
from statsmodels.stats.outliers_influence import variance_inflation_factor
import pingouin as pg
import os

# ----------------------------------------------------------------------
# Helper functions for CGAM Pipeline: VIF, CGAM, Cohen's
def compute_vif(df, feature_cols, vif_threshold=10, export=True):
    """
    Compute VIF and remove features with high collinearity.

    Parameters:
    df (pd.DataFrame): DataFrame containing feature columns.
    feature_cols (list): List of feature column names.
    vif_threshold (float): Threshold for removing features with high VIF.

    Returns:
    list: List of selected features after VIF filtering.
    """
    selected_features = feature_cols.copy()
    
    while len(selected_features) > 1:
        X = df[selected_features].to_numpy()
        vif_values = [variance_inflation_factor(X, i) for i in range(X.shape[1])]
        
        # Create a DataFrame for VIF values
        vif_df = pd.DataFrame({"Feature": selected_features, "VIF": vif_values})
        max_vif = vif_df["VIF"].max()
        
        # Stop if all VIF values are below the threshold
        if max_vif < vif_threshold:
            break
        
        # Drop the feature with the highest VIF
        drop_feature = vif_df.loc[vif_df["VIF"].idxmax(), "Feature"]
        selected_features.remove(drop_feature)
        print(f"Dropping '{drop_feature}' with VIF={max_vif:.2f}")
    if export:   
        # EXPORT SELECTED FEATURES
        export_path = r"Y:\LabMembers\Ameen\Stroke-R01-Aim-2\SavedOutcomesAim2\Overground_EMG_Kinematics\2_FromPython_CGAM"
        os.makedirs(export_path, exist_ok=True)
        txt_file = os.path.join(export_path, "Selected_Features_After_VIF.txt")

        with open(txt_file, "w") as f:
            f.write("Selected Features After VIF Filtering:\n")
            f.write("\n".join(selected_features))

        print(f"\nExported {len(selected_features)} selected features to:\n{txt_file}\n")
    
    return selected_features

def calculate_cgam_grouped(df, groupby_cols, feature_cols):
    
    """
    Compute CGAM using features selected from VIF.

    Parameters:
    df (pd.DataFrame): DataFrame containing symmetry data.
    feature_cols (list): List of feature column names.
    groupby_cols (list): List of columns to group by (e.g., ['Subject', 'Intervention'])

    Returns:
    df: DataFrame with CGAM values for each stride, grouped by specified columns.
    """
    results = []
    grouped = df.groupby(groupby_cols)

    for group_name, group_df in grouped:
        if len(group_df) < 3:
            print(f"Skipped group: {group_name} (only {len(group_df)} strides)")
            continue

        # Symmetry matrix S: (strides x features)
        S = group_df[feature_cols].to_numpy()

        # Covariance matrix across all strides (features x features)
        K_S = np.cov(S, rowvar=False, bias=False)
        
        cond_number = np.linalg.cond(K_S)
        if cond_number > 1e10:
            print("Warning: Matrix is ill-conditioned")
            print(f"Skipped group: {group_name} (only {len(group_df)} strides)")
            print(f"Group {group_name} | strides={len(group_df)} | cond={cond_number:.2e}")
            print("Feature Standard Deviation:", group_df[feature_cols].std().round(2).to_dict())
            print("Feature Average:", group_df[feature_cols].mean().round(2).to_dict())

            continue

        # Inverse covariance matrix
        K_S_inv = np.linalg.inv(K_S)

        denominator = np.sum(K_S_inv)

        # Compute CGAM for each stride
        for i, stride_S in enumerate(S):
            numerator = stride_S @ K_S_inv @ stride_S.T
            val = numerator / denominator
            if val < 0 or np.isnan(val):
                print(f"Warning: Invalid value inside sqrt in group {group_name}. Skipping stride {i}.")
                continue
            cgam_value = np.sqrt(val)

            # Collect metadata columns for this stride
            cycle_val = group_df['Cycle'].iloc[i]
            trial_val = group_df['Trial'].iloc[i]


            # Append all data
            results.append((*group_name, trial_val, cycle_val, cgam_value))


    # Create DataFrame with results
    result_df = pd.DataFrame(results, columns=groupby_cols + ['Trial','Cycle','CGAM'])
    return result_df

def cohens_d(df, features, timepoints, 
             group_keys=['Subject'],
             paired=False, smaller_is_better=True):
    """
    Compute Cohen's d between BL and every other intervention for each group.

    Parameters
    ----------
    df : DataFrame with 'Intervention' + group_keys + features
    features : list of feature names
    timepoints : ordered list of interventions
    group_keys : grouping columns (default = subject/condition info)
    paired : use paired Cohen's d if trials align
    smaller_is_better : flip sign so positive = improvement
    """
    results = []
    grouped = df.groupby(group_keys)

    for key, group in grouped:
        row = dict(zip(group_keys, key))
        times = [tp for tp in timepoints if tp in group['Intervention'].values]
        if 'BL' not in times or len(times) < 2:
            continue

        baseline = group[group['Intervention'] == 'BL']

        for t2 in times:
            if t2 == 'BL':
                continue
            g2 = group[group['Intervention'] == t2]
            for f in features:
                v1, v2 = baseline[f].dropna(), g2[f].dropna()
                if len(v1) and len(v2):
                    d = pg.compute_effsize(v1, v2, paired=paired, eftype='cohen')
                    if smaller_is_better:
                        d = -d
                    row[f"{f}_BL_to_{t2}"] = d
                else:
                    row[f"{f}_BL_to_{t2}"] = None

        results.append(row)

    return pd.DataFrame(results)




# ----------------------------------------------------------------------
# CGAM Pipeline Class
class CGAMPipeline:
    def __init__(self, data_path):
        self.data_path = data_path
        self.df = None
        self.filtered_df = None
        self.feature_cols = []
        self.vif_features = []
        self.cgam_matrix = None

    def load_and_filter_data(self, speed='FV'):
        self.df = pd.read_csv(self.data_path)
        
        # Filter by speed
        self.filtered_df = self.df[self.df['Speed'] == speed].copy()
        
        # Filter out features not going to be used in CGAM (Before VIF)
        drop_cols = [
            'StanceDurations_GR_Sym', 'StrideWidths_GR_Sym',
            'Single_Support_Time_GR_Sym', 'Double_Support_Time_GR_Sym'
        ]
        self.filtered_df.drop(columns=drop_cols, inplace=True, errors='ignore')

        
        # Robustness check - confirm that there are no significant missing values in the dataset
        missing_counts = self.filtered_df.isnull().sum()
        filtered_missing = missing_counts[missing_counts > 0]
        if not filtered_missing.empty:
            print("Missing data detected:")
            print(filtered_missing)
        else:
            print("No missing data found.")

        print(f"Data loaded and filtered: Speed={speed}")

    # Filter out EMG and Kinematic features not going to be used in CGAM (Before VIF)
    def extract_feature_cols(self, feature_type: str = 'all'):
        # Base filter
        feature_cols = [
            col for col in self.filtered_df.columns
            # if (
            #     isinstance(col, str) and 'Sym' in col and
            #     col != 'NumSynergies_Sym' and
            #     all(x not in col for x in [
            #         'RMSE_EMG', 'Lag_EMG', 'Mag_EMG',
            #         'AUC_EMG', 'RMS_EMG',
            #         'AUC_JointAngles', 'JointAngles_Max', 'JointAngles_Min'
            #     ])
            # )
            if (
                isinstance(col, str) and 'Sym' in col and
                col != 'NumSynergies_Sym' and
                all(x not in col for x in [
                 'JointAngles_Max', 'JointAngles_Min',
                ])
            )
        ]

        # Apply conditional filters
        if feature_type == 'gait':
            feature_cols = [c for c in feature_cols if 'JointAngles' not in c and 'EMG' not in c]
            print(f"Gait features selected: {feature_cols}")
        elif feature_type == 'joint':
            feature_cols = [c for c in feature_cols if 'EMG' not in c and 'GR' not in c]
            print(f"Joint features selected: {feature_cols}")
        elif feature_type == 'emg':
            feature_cols = [c for c in feature_cols if 'JointAngles' not in c and 'GR' not in c]
            print(f"EMG features selected: {feature_cols}")
        elif feature_type == 'all':
            pass  # keep as is
        else:
            raise ValueError(f"Invalid feature_type '{feature_type}'. Must be one of: 'all', 'gait', 'joint', 'emg'.")

        # Safety check: if empty, raise descriptive error
        if not feature_cols:
            if feature_type == 'gait':
                raise ValueError("No features found in GaitRite.")
            elif feature_type == 'joint':
                raise ValueError("No features found in JointAngles.")
            elif feature_type == 'emg':
                raise ValueError("No features found in EMG.")
            else:
                raise ValueError("No features found after filtering.")
            
            
        # Drop rows with NaNs only in selected features
        self.filtered_df.dropna(subset=feature_cols, inplace=True)

        # Save to class
        self.feature_cols = feature_cols


    # Extract features no dropped by VIF
    def compute_vif_features(self):
        df_demeaned = self.filtered_df.copy()
        df_demeaned[self.feature_cols] = df_demeaned[self.feature_cols].apply(lambda x: x - x.mean())
        print("Starting VIF computation...")
        self.vif_features = compute_vif(df_demeaned, self.feature_cols, vif_threshold=5, export=True)


    # Compute CGAM using features selected from VIF
    def compute_cgam(self, groupby_cols):
        # Keep group keys columns along with VIF features
        group_keys = groupby_cols + ['Trial', 'Cycle']
        self.filtered_df_vif = self.filtered_df[group_keys + self.vif_features].copy()
        print("Calculating CGAM...")
        self.cgam_matrix = calculate_cgam_grouped(self.filtered_df, groupby_cols, self.vif_features)
        print("CGAM calculation complete.")
        return self.cgam_matrix, self.filtered_df_vif
    # Compute Cohen's d for Pre-Post CGAM values
    def get_cohens_d(self, features=['CGAM', 'StepLengths_GR_Sym', 'SwingDurations_GR_Sym'], timepoints=None):
        """
        Compute Cohen's d on CGAM values across interventions.
        """
        if timepoints is None:
            # Default to all interventions present in cgam_matrix
            timepoints = self.cgam_matrix['Intervention'].unique().tolist()

        print("Calculating Cohen's d across interventions...")

        cohens_df = cohens_d(self.cgam_matrix, features, timepoints,
                            group_keys=['Subject'], 
                            paired=False, 
                            smaller_is_better=True)
        
        print("Cohen's d calculation complete.")
        return cohens_df
        
    def run_random_feature_stability(self, n_samples=1000, subset_size=15, groupby_cols=None,
                                     export_path=r"..\..\SavedOutcomesAim2\Overground_EMG_Kinematics\2_FromPython_CGAM"):
        """
        Generate n_samples random feature subsets (each of size subset_size),
        run VIF + CGAM for each subset, and export CGAM values for stability analysis.
        """

        if groupby_cols is None:
            groupby_cols = ['Subject', 'Intervention', 'Speed']

        all_features = self.feature_cols.copy()

        if len(all_features) < subset_size:
            raise ValueError(f"Subset size {subset_size} is larger than available features ({len(all_features)})")

        os.makedirs(export_path, exist_ok=True)

        stability_results = []  # will hold CGAM results for all runs

        print(f"\n=== Running {n_samples} Random Feature Subset Stability Experiments ===")
        print(f"Total available features: {len(all_features)}")
        print(f"Random subset size: {subset_size}\n")

        for i in range(n_samples):
    
            # Random subset of features
            random_subset = list(np.random.choice(all_features, size=subset_size, replace=False))

            
            # Apply VIF to the subset
            df_demeaned = self.filtered_df.copy()
            df_demeaned[random_subset] = df_demeaned[random_subset].apply(lambda x: x - x.mean())

            try:
                vif_selected = compute_vif(df_demeaned, random_subset, vif_threshold=5, export=False)
            except Exception as e:
                print(f"[Warning] VIF failed for subset {i}. Skipping. Error: {e}")
                continue

            if len(vif_selected) < 2:
                print(f"[Warning] Less than 2 features after VIF for sample {i}. Skipping.")
                continue

        
            # Compute CGAM on VIF-selected subset
            try:
                cgam_i = calculate_cgam_grouped(self.filtered_df, groupby_cols, vif_selected)
            except Exception as e:
                print(f"[Warning] CGAM failed for subset {i}. Skipping. Error: {e}")
                continue

            if cgam_i.empty:
                print(f"[Warning] Empty CGAM result for subset {i}. Skipping.")
                continue

            # Add run index & selected features
            cgam_i["Run"] = i
            cgam_i["SelectedFeatures"] = [",".join(vif_selected)] * len(cgam_i)

            stability_results.append(cgam_i)

        # Combine & Export all CGAM stability runs
        if stability_results:
            stability_df = pd.concat(stability_results, ignore_index=True)

            out_csv = os.path.join(export_path, "CGAM_Stability_1000Runs.csv")
            stability_df.to_csv(out_csv, index=False)

            print(f"\nSUCCESS")
            print(f"Exported CGAM stability results to:\n{out_csv}")
            return stability_df
        else:
            print("No successful CGAM runs were produced.")
            return pd.DataFrame()



    
    

# ----------------------------------------------------------------------
# Main callable function to run the CGAM pipeline
def run_CGAM_pipeline(data_path, speed='FV', feature_type='all', time_order = ["BL","MID18","MID24","POST18","POST24", "MO1FU", "MO3FU"]):
    """
    Function to call CGAM Pipeline.

    Parameters:
    data_path (path): Matched cycles symmetry data with 10MWT
    speed (string): 'SSV' or 'FV' for speed of interest.
    include_sham1 (bool): If True, includes SHAM1 intervention in the analysis.

    Returns:
    pd.DataFrame for CGAM values, and Cohen's d for Pre vs Post.
    """
    groupby_cols = ['Subject', 'Intervention', 'Speed']

    pipeline = CGAMPipeline(data_path)
    pipeline.load_and_filter_data(speed=speed)
    pipeline.extract_feature_cols(feature_type = feature_type)
    pipeline.compute_vif_features()
    cgam_df, filtered_df = pipeline.compute_cgam(groupby_cols)
    cohens_df = pipeline.get_cohens_d(features=['CGAM'], timepoints=time_order)

    return cgam_df, cohens_df, filtered_df
