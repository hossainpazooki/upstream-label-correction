/**
 * MCP Tool registry — maps tool names to handlers and schemas.
 * Each handler calls the Python ML service via HTTP.
 */

import { z } from "zod";
import * as mlClient from "@/lib/ml-client";
import {
  LoadDatasetInput,
  ImputeMissingInput,
  CheckAvailabilityInput,
  SelectBiomarkersInput,
  RunClassificationInput,
  MatchCrossOmicsInput,
  EvaluateModelInput,
  ExplainFeaturesInput,
  ExplainFeaturesLocalInput,
} from "@/lib/schemas/omics";

export interface ToolDefinition {
  description: string;
  inputSchema: Record<string, unknown>;
  handler: (args: Record<string, unknown>) => Promise<Record<string, unknown>>;
}

function zodToJsonSchema(schema: z.ZodType): Record<string, unknown> {
  // Simplified JSON schema extraction — in production use zod-to-json-schema
  return {
    type: "object",
    properties: {},
  };
}

export const TOOL_REGISTRY: Record<string, ToolDefinition> = {
  load_dataset: {
    description:
      "Load a multi-omics dataset (clinical, proteomics, RNA-Seq) and return summary statistics.",
    inputSchema: zodToJsonSchema(LoadDatasetInput),
    handler: async (args) => {
      const input = LoadDatasetInput.parse(args);
      // Proxy to ML service — data loading requires Python
      return mlClient.impute({
        dataset: input.dataset,
        modality: "proteomics",
      }) as unknown as Promise<Record<string, unknown>>;
    },
  },

  impute_missing: {
    description:
      "Classify missing values as MNAR or MAR and impute using NMF.",
    inputSchema: zodToJsonSchema(ImputeMissingInput),
    handler: async (args) => {
      const input = ImputeMissingInput.parse(args);
      return mlClient.impute(input) as unknown as Promise<Record<string, unknown>>;
    },
  },

  check_availability: {
    description:
      "Check gene availability and filter by coverage threshold.",
    inputSchema: zodToJsonSchema(CheckAvailabilityInput),
    handler: async (args) => {
      const input = CheckAvailabilityInput.parse(args);
      // This needs ML service support — will be added as /ml/availability
      const ML_URL = process.env.ML_SERVICE_URL ?? "http://localhost:8000";
      const res = await fetch(`${ML_URL}/ml/availability`, {
        method: "POST",
        headers: mlClient.mlHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(input),
      });
      return res.json();
    },
  },

  select_biomarkers: {
    description:
      "Run multi-strategy biomarker selection (ANOVA, LASSO, NSC, RF) with ensemble integration.",
    inputSchema: zodToJsonSchema(SelectBiomarkersInput),
    handler: async (args) => {
      const input = SelectBiomarkersInput.parse(args);
      return mlClient.selectFeatures(input) as unknown as Promise<Record<string, unknown>>;
    },
  },

  run_classification: {
    description:
      "Train an ensemble mismatch classifier and evaluate with cross-validation.",
    inputSchema: zodToJsonSchema(RunClassificationInput),
    handler: async (args) => {
      const input = RunClassificationInput.parse(args);
      return mlClient.classify(input) as unknown as Promise<Record<string, unknown>>;
    },
  },

  match_cross_omics: {
    description:
      "Build cross-omics distance matrix and identify sample mismatches.",
    inputSchema: zodToJsonSchema(MatchCrossOmicsInput),
    handler: async (args) => {
      const input = MatchCrossOmicsInput.parse(args);
      return mlClient.matchCrossOmics(input) as unknown as Promise<Record<string, unknown>>;
    },
  },

  evaluate_model: {
    description:
      "Evaluate a trained classifier on holdout data (F1, precision, recall, ROC-AUC).",
    inputSchema: zodToJsonSchema(EvaluateModelInput),
    handler: async (args) => {
      const input = EvaluateModelInput.parse(args);
      return mlClient.evaluate(input) as unknown as Promise<Record<string, unknown>>;
    },
  },

  explain_features: {
    description:
      "Generate biological explanations for biomarker genes using pathway knowledge + LLM.",
    inputSchema: zodToJsonSchema(ExplainFeaturesInput),
    handler: async (args) => {
      const input = ExplainFeaturesInput.parse(args);
      const ML_URL = process.env.ML_SERVICE_URL ?? "http://localhost:8000";
      const res = await fetch(`${ML_URL}/ml/explain`, {
        method: "POST",
        headers: mlClient.mlHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(input),
      });
      return res.json();
    },
  },

  explain_features_local: {
    description:
      "Generate explanations using the fine-tuned SLM (BioMistral).",
    inputSchema: zodToJsonSchema(ExplainFeaturesLocalInput),
    handler: async (args) => {
      const input = ExplainFeaturesLocalInput.parse(args);
      const ML_URL = process.env.ML_SERVICE_URL ?? "http://localhost:8000";
      const res = await fetch(`${ML_URL}/ml/explain-local`, {
        method: "POST",
        headers: mlClient.mlHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(input),
      });
      return res.json();
    },
  },
};
