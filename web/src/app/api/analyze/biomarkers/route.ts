import { NextRequest, NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { v4 as uuidv4 } from "uuid";
import { prisma } from "@/lib/prisma";
import { BiomarkerDiscoveryParams } from "@/lib/schemas/workflows";
import { enqueuePipeline } from "@/lib/ml-queue";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const params = BiomarkerDiscoveryParams.parse(body);
  const workflowId = `biomarker-${uuidv4().slice(0, 12)}`;

  // Create workflow execution record
  const workflow = await prisma.workflowExecution.create({
    data: {
      id: workflowId,
      workflowType: "biomarker_discovery",
      status: "pending",
      params: params as unknown as Prisma.InputJsonValue,
      phasesRemaining: [
        "data_loading",
        "imputation",
        "feature_selection",
        "classification",
        "cross_omics",
        "interpretation",
      ],
    },
  });

  // Enqueue pipeline job
  await enqueuePipeline({
    workflowId,
    dataset: params.dataset,
    target: params.target,
    modalities: params.modalities,
    n_top_features: params.n_top_features,
    cv_folds: params.cv_folds,
  });

  return NextResponse.json({
    workflow_id: workflow.id,
    status: workflow.status,
    message: "Biomarker discovery workflow queued",
  });
}
