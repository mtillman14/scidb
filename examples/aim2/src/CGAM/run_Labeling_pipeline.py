import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import ttest_rel
from matplotlib import cm

# Helper to count binary labels
def print_binary_label_counts_from_labels(df, column_name, true_label, false_label, description):
    print(f"\n{description}:")
    print(f"{true_label}:", (df[column_name] == 1).sum())
    print(f"{false_label}:", (df[column_name] == 0).sum())


# Main labeling and stats pipeline
def run_labeling_pipeline(cohens_df, plot=False):
    
    # relabel_dict = {'SS06':'TOL50', 'SS10':'TOL50','SS01':'TOL30'}
    # for subject, intervention in relabel_dict.items():
    #     mask = (cohens_df['Subject'] == subject) & (cohens_df['Intervention'] == intervention)
    #     cohens_df.loc[mask, 'Intensity'] = 'RMT'

    features = ['CGAM']

    # Segment Stim/NoStim. Each subject should have 4 values, one per intervention.
    cohens_stim = cohens_df[cohens_df["Is_Stim"] == 'STIM']
    cohens_nostim = cohens_df[cohens_df["Is_Stim"] == 'NOSTIM']

    # Get max CGAM for stim condition per subject
    idx_stim = cohens_stim.groupby('Subject')['CGAM'].idxmax()
    cohens_maxStim = cohens_stim.loc[idx_stim, ['Subject', 'SessionOrder', 'Intervention', 'CGAM']]
    # Combine max stim and no stim values into one data frame. One value per subject.
    best_stim_nostim = pd.merge(
        cohens_maxStim[['Subject', 'Intervention', 'CGAM']],
        cohens_nostim[['Subject', 'Intervention', 'CGAM']],
        on='Subject',
        suffixes=('_stim', '_nostim')
    )

    # Segment Intensity
    cohens_tol = cohens_df[cohens_df["Intensity"] == 'TOL']
    cohens_rmt = cohens_df[cohens_df["Intensity"] == 'RMT']
    cohens_meanTOL = cohens_tol.groupby('Subject')[features].mean().reset_index()
    cohens_meanRMT = cohens_rmt.groupby('Subject')[features].mean().reset_index()
    # cohens_meanTOL = cohens_tol.groupby('Subject')[features].max().reset_index()
    # cohens_meanRMT = cohens_rmt.groupby('Subject')[features].max().reset_index()
    best_intensity = pd.merge(cohens_meanTOL, cohens_meanRMT, on='Subject', suffixes=('_TOL', '_RMT'))
    # best_intensity = best_intensity[best_intensity['Subject'] != 'SS27']

    # Segment Frequency
    cohens_30 = cohens_df[cohens_df["Frequency"] == 30]
    cohens_50 = cohens_df[cohens_df["Frequency"] == 50]
    cohens_mean30 = cohens_30.groupby('Subject')[features].mean().reset_index()
    cohens_mean50 = cohens_50.groupby('Subject')[features].mean().reset_index()
    # cohens_mean30 = cohens_30.groupby('Subject')[features].max().reset_index()
    # cohens_mean50 = cohens_50.groupby('Subject')[features].max().reset_index()
    best_frequency = pd.merge(cohens_mean30, cohens_mean50, on='Subject', suffixes=('_30', '_50'))

    # T-tests
    stim_vals = best_stim_nostim['CGAM_stim']
    nostim_vals = best_stim_nostim['CGAM_nostim']
    t_stat_stim, p_val_stim = ttest_rel(stim_vals, nostim_vals)

    tol_vals = best_intensity['CGAM_TOL']
    rmt_vals = best_intensity['CGAM_RMT']
    t_stat_intensity, p_val_intensity = ttest_rel(tol_vals, rmt_vals)

    vals30 = best_frequency['CGAM_30']
    vals50 = best_frequency['CGAM_50']
    t_stat_freq, p_val_freq = ttest_rel(vals30, vals50)

    ttest_results = pd.DataFrame([
        {
            'Test': 'Stim vs NoStim',
            'p-value': p_val_stim,
            'Stim Mean': stim_vals.mean(),
            'NoStim Mean': nostim_vals.mean()
        },
        {
            'Test': 'TOL vs RMT',
            'p-value': p_val_intensity,
            'TOL Mean': tol_vals.mean(),
            'RMT Mean': rmt_vals.mean()
        },
        {
            'Test': '30 Hz vs 50 Hz',
            'p-value': p_val_freq,
            '30 Hz Mean': vals30.mean(),
            '50 Hz Mean': vals50.mean()
        }
    ])

    # Labels
    stim_condition = (stim_vals > nostim_vals)
    stim_labels = pd.DataFrame({
        'Subject': best_stim_nostim['Subject'],
        'Stim Label': (~stim_condition).astype(int)
    })

    intensity_condition = (tol_vals > rmt_vals)
    intensity_labels = pd.DataFrame({
        'Subject': best_intensity['Subject'],
        'Intensity Label': intensity_condition.astype(int)
    })
    # Manually label SS27 as RMT (Intensity Label = 0)
    # intensity_labels = pd.concat([
    #     intensity_labels,
        # pd.DataFrame({'Subject': ['SS27'], 'Intensity Label': [0]})
    # ], ignore_index=True)

    frequency_condition = (vals30 > vals50)
    frequency_labels = pd.DataFrame({
        'Subject': best_frequency['Subject'],
        'Frequency Label': frequency_condition.astype(int)
    })

    # Align all to same subject order
    subject_order = sorted(set(stim_labels['Subject']) & set(intensity_labels['Subject']) & set(frequency_labels['Subject']))
    stim_labels = stim_labels.set_index('Subject').reindex(subject_order).reset_index()
    intensity_labels = intensity_labels.set_index('Subject').reindex(subject_order).reset_index()
    frequency_labels = frequency_labels.set_index('Subject').reindex(subject_order).reset_index()

    labels_df = stim_labels.merge(intensity_labels, on='Subject')
    labels_df = labels_df.merge(frequency_labels, on='Subject')

    # Print counts
    print_binary_label_counts_from_labels(stim_labels, "Stim Label", "Stim", "NoStim", "Stim vs NoStim")
    print_binary_label_counts_from_labels(intensity_labels, "Intensity Label", "TOL", "RMT", "TOL vs RMT")
    print_binary_label_counts_from_labels(frequency_labels, "Frequency Label", "30 Hz", "50 Hz", "30 Hz vs 50 Hz")


    # Optional Plotting
    if plot:
        _plot_ttests(stim_vals, nostim_vals, p_val_stim, 'Stim', 'No Stim', 'Stim vs No Stim')
        _plot_ttests(tol_vals, rmt_vals, p_val_intensity, 'TOL', 'RMT', 'TOL vs RMT')
        _plot_ttests(vals30, vals50, p_val_freq, '30 Hz', '50 Hz', '30 Hz vs 50 Hz')

    return ttest_results, labels_df

# Reusable plotting function
def _plot_ttests(group1, group2, p_val, label1, label2, title):
    fig, ax = plt.subplots(figsize=(6, 5))
    x_pos = [0, 1]
    means = [np.mean(group1), np.mean(group2)]
    stds = [np.std(group1, ddof=1), np.std(group2, ddof=1)]

    ax.errorbar(x_pos, means, yerr=stds, fmt='o', capsize=6, color='black', markersize=8, elinewidth=1.8)

    if p_val < 0.05:
        y = max(means) + 0.05 * max(means)
        ax.plot([x_pos[0], x_pos[0], x_pos[1], x_pos[1]], [y, y+0.01, y+0.01, y], lw=1.5, color='black')
        ax.text(np.mean(x_pos), y + 0.015, f'* (p = {p_val:.4f})', ha='center', va='bottom', fontsize=11)

    ax.set_xticks(x_pos)
    ax.set_xticklabels([label1, label2])
    ax.set_ylabel("Cohen's d (CGAM)")
    ax.set_title(title)
    plt.tight_layout()
    plt.show()
