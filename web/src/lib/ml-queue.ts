/**
 * Redis-based job queue (BullMQ) for long-running ML operations.
 * Used for: full pipeline, training, DSPy compilation.
 */

import { Queue, Worker, Job } from "bullmq";

const REDIS_URL = process.env.REDIS_URL ?? "redis://localhost:6379/0";

function getConnectionOptions() {
  const url = new URL(REDIS_URL);
  return {
    host: url.hostname,
    port: parseInt(url.port || "6379", 10),
    password: url.password || undefined,
    db: parseInt(url.pathname.slice(1) || "0", 10),
    maxRetriesPerRequest: null as null,
  };
}

// --- Queue Definitions ---

export const mlPipelineQueue = new Queue("ml-pipeline", {
  connection: getConnectionOptions(),
  defaultJobOptions: {
    attempts: 3,
    backoff: { type: "exponential", delay: 5000 },
    removeOnComplete: { age: 86400 }, // 24h
    removeOnFail: { age: 604800 }, // 7d
  },
});

export const trainingQueue = new Queue("ml-training", {
  connection: getConnectionOptions(),
  defaultJobOptions: {
    attempts: 1,
    removeOnComplete: { age: 604800 },
    removeOnFail: { age: 604800 },
  },
});

// --- Job Types ---

export type PipelineJobData = {
  workflowId: string;
  dataset?: string;
  target?: string;
  modalities?: string[];
  n_top_features?: number;
  cv_folds?: number;
};

export type TrainingJobData = {
  workflowId: string;
  trainingType: "slm" | "encoder" | "classifier";
  config: Record<string, unknown>;
};

// --- Enqueue Functions ---

export async function enqueuePipeline(data: PipelineJobData): Promise<string> {
  const job = await mlPipelineQueue.add("run-pipeline", data, {
    jobId: data.workflowId,
  });
  return job.id ?? data.workflowId;
}

export async function enqueueTraining(data: TrainingJobData): Promise<string> {
  const job = await trainingQueue.add("run-training", data, {
    jobId: data.workflowId,
  });
  return job.id ?? data.workflowId;
}

// --- Job Status ---

export async function getJobStatus(
  queueName: string,
  jobId: string,
): Promise<{
  status: string;
  progress: number;
  result?: unknown;
  error?: string;
} | null> {
  const queue =
    queueName === "ml-pipeline" ? mlPipelineQueue : trainingQueue;
  const job = await Job.fromId(queue, jobId);
  if (!job) return null;

  const state = await job.getState();
  return {
    status: state,
    progress: (job.progress as number) ?? 0,
    result: job.returnvalue,
    error: job.failedReason,
  };
}
