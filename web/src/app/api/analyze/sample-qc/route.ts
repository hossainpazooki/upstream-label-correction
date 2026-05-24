import { NextRequest, NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { v4 as uuidv4 } from "uuid";
import { prisma } from "@/lib/prisma";
import { SampleQCParams } from "@/lib/schemas/workflows";
import { enqueuePipeline } from "@/lib/ml-queue";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const params = SampleQCParams.parse(body);
  const workflowId = `sample-qc-${uuidv4().slice(0, 12)}`;

  const workflow = await prisma.workflowExecution.create({
    data: {
      id: workflowId,
      workflowType: "sample_qc",
      status: "pending",
      params: params as unknown as Prisma.InputJsonValue,
      phasesRemaining: [
        "data_loading",
        "classification",
        "distance_matching",
        "concordance",
      ],
    },
  });

  await enqueuePipeline({
    workflowId,
    dataset: params.dataset,
  });

  return NextResponse.json({
    workflow_id: workflow.id,
    status: workflow.status,
    message: "Sample QC workflow queued",
  });
}
