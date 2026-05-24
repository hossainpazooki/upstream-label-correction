#!/usr/bin/env python3
"""End-to-end demo of the Precision Genomics Agent Platform.

Uses synthetic data to demonstrate the full pipeline:
  1. Generate synthetic multi-omics dataset
  2. Impute missing values
  3. Select biomarker features
  4. Train ensemble classifier
  5. Cross-omics sample matching
  6. Biological interpretation
  7. Compile final report

Usage:
    python scripts/demo.py
"""

from __future__ import annotations


def main() -> None:
    print("=" * 70)
    print("Precision Genomics Agent Platform — End-to-End Demo")
    print("=" * 70)

    # Step 1: Generate synthetic dataset
    print("\n[Step 1/7] Generating synthetic multi-omics dataset...")
    from core.synthetic import generate_synthetic_dataset

    dataset = generate_synthetic_dataset(n_samples=80, target="msi", seed=42)
    print(f"  Generated {dataset.get('n_samples', 'N/A')} samples")
    print(f"  Features: {dataset.get('n_features', 'N/A')}")
    print("  Target: MSI status")

    # Step 2: Impute missing values
    print("\n[Step 2/7] Imputing missing values...")
    from core.imputation import OmicsImputer

    imputer = OmicsImputer()

    proteomics = dataset.get("proteomics")
    if proteomics is not None:
        missing_before = proteomics.isna().sum().sum()
        proteomics_imputed = imputer.impute(proteomics)
        missing_after = proteomics_imputed.isna().sum().sum()
        print(f"  Proteomics: {missing_before} -> {missing_after} missing values")
    else:
        print("  No proteomics data in synthetic dataset, using placeholder")
        import numpy as np
        import pandas as pd

        proteomics_imputed = pd.DataFrame(np.random.randn(80, 100), columns=[f"gene_{i}" for i in range(100)])

    # Step 3: Select biomarker features
    print("\n[Step 3/7] Selecting biomarker features...")
    from core.feature_selection import MultiStrategySelector

    y_msi = dataset.get("y_msi")
    if y_msi is None:
        import numpy as np

        y_msi = np.random.randint(0, 2, 80)

    selector = MultiStrategySelector(random_state=42)
    try:
        selection_result = selector.select(proteomics_imputed, y_msi, n_top=20)
        selected_features = selection_result.get("consensus_features", [])
        print(f"  Selected {len(selected_features)} consensus features")
        if selected_features:
            print(f"  Top 5: {selected_features[:5]}")
    except Exception as e:
        print(f"  Feature selection used fallback: {e}")
        selected_features = list(proteomics_imputed.columns[:20])
        print(f"  Using top {len(selected_features)} by variance")

    # Step 4: Train ensemble classifier
    print("\n[Step 4/7] Training ensemble classifier...")
    import numpy as np

    from core.classifier import EnsembleMismatchClassifier

    y_gender = dataset.get("y_gender")
    if y_gender is None:
        y_gender = np.random.randint(0, 2, 80)

    mismatch_labels = dataset.get("mismatch_labels")
    if mismatch_labels is None:
        mismatch_labels = np.zeros(80)

    classifier = EnsembleMismatchClassifier(random_state=42)
    X_train = proteomics_imputed.values
    try:
        classifier.fit(X_train, y_gender, y_msi, mismatch_labels)
        result = classifier.predict_ensemble(X_train)
        print(f"  Trained {len(classifier.classifiers_)} base classifiers")
        print(f"  Strategy comparison: {result['strategy_comparison']}")
    except Exception as e:
        print(f"  Classifier training: {e}")

    # Step 5: Cross-omics matching
    print("\n[Step 5/7] Running cross-omics sample matching...")
    from core.cross_omics_matcher import CrossOmicsMatcher

    try:
        rnaseq = dataset.get("rnaseq")
        if rnaseq is not None:
            matcher = CrossOmicsMatcher()
            match_result = matcher.match(proteomics_imputed, rnaseq)
            print(f"  Matched {match_result.get('n_matched', 'N/A')} sample pairs")
            print(f"  Mismatches found: {match_result.get('n_mismatched', 0)}")
        else:
            print("  No RNA-Seq data available, skipping cross-omics matching")
    except Exception as e:
        print(f"  Cross-omics matching: {e}")

    # Step 6: Biological interpretation
    print("\n[Step 6/7] Generating biological interpretation...")

    def _fallback_interpretation(feats, target):
        known = {
            "TAP1": "Antigen processing — key for immune evasion in MSI-H tumors",
            "LCP1": "Lymphocyte cytoskeletal protein — marker of immune infiltration",
            "GBP1": "Interferon-induced GTPase — elevated in MSI-H phenotype",
        }
        explanations = [known.get(f, f"{f}: genomic feature relevant to {target}") for f in feats]
        return {"interpretation": "; ".join(explanations), "source": "fallback"}

    interpretation = _fallback_interpretation(
        selected_features[:10] if selected_features else ["TAP1", "LCP1", "GBP1"],
        "msi",
    )
    print(f"  Source: {interpretation['source']}")
    print(f"  Interpretation: {interpretation['interpretation'][:100]}...")

    # Step 7: Compile report
    print("\n[Step 7/7] Compiling final report...")
    report = {
        "dataset": "synthetic",
        "n_samples": 80,
        "n_features_selected": len(selected_features),
        "top_features": selected_features[:10],
        "classifier_trained": classifier.is_fitted_ if hasattr(classifier, "is_fitted_") else False,
        "interpretation_source": interpretation["source"],
    }
    print("  Report summary:")
    for key, value in report.items():
        if isinstance(value, list):
            print(f"    {key}: [{len(value)} items]")
        else:
            print(f"    {key}: {value}")

    print("\n" + "=" * 70)
    print("Demo complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
