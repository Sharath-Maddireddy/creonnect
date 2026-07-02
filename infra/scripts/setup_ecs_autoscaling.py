#!/usr/bin/env python3
"""Configure ECS auto-scaling for the Creonnect SQS worker.

Usage:
    python infra/scripts/setup_ecs_autoscaling.py

Env vars (all optional, have defaults):
    ECS_CLUSTER, ECS_SERVICE, SQS_QUEUE_NAME,
    WORKER_MIN_TASKS, WORKER_MAX_TASKS,
    SCALE_OUT_THRESHOLD, SCALE_IN_THRESHOLD, AWS_REGION
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Final

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError


@dataclass(frozen=True)
class Config:
    region: str
    ecs_cluster: str
    ecs_service: str
    sqs_queue_name: str
    worker_min_tasks: int
    worker_max_tasks: int
    scale_out_threshold: int
    scale_in_threshold: int


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid integer for {name}: {raw!r}")


def _load_config() -> Config:
    return Config(
        region=os.getenv("AWS_REGION", "ap-south-1").strip() or "ap-south-1",
        ecs_cluster=os.getenv("ECS_CLUSTER", "creonnect-prod").strip() or "creonnect-prod",
        ecs_service=os.getenv("ECS_SERVICE", "creonnect-worker").strip() or "creonnect-worker",
        sqs_queue_name=os.getenv("SQS_QUEUE_NAME", "account-analysis").strip() or "account-analysis",
        worker_min_tasks=_read_int_env("WORKER_MIN_TASKS", 1),
        worker_max_tasks=_read_int_env("WORKER_MAX_TASKS", 8),
        scale_out_threshold=_read_int_env("SCALE_OUT_THRESHOLD", 5),
        scale_in_threshold=_read_int_env("SCALE_IN_THRESHOLD", 1),
    )


def _validate_config(config: Config) -> None:
    if config.worker_min_tasks < 0:
        raise ValueError("WORKER_MIN_TASKS must be >= 0")
    if config.worker_max_tasks < config.worker_min_tasks:
        raise ValueError("WORKER_MAX_TASKS must be >= WORKER_MIN_TASKS")
    if config.scale_out_threshold < 0:
        raise ValueError("SCALE_OUT_THRESHOLD must be >= 0")
    if config.scale_in_threshold < 0:
        raise ValueError("SCALE_IN_THRESHOLD must be >= 0")


def _register_scalable_target(app_asg_client: BaseClient, config: Config) -> str:
    resource_id = f"service/{config.ecs_cluster}/{config.ecs_service}"
    app_asg_client.register_scalable_target(
        ServiceNamespace="ecs",
        ResourceId=resource_id,
        ScalableDimension="ecs:service:DesiredCount",
        MinCapacity=config.worker_min_tasks,
        MaxCapacity=config.worker_max_tasks,
    )
    return resource_id


def _put_scale_out_policy(app_asg_client: BaseClient, config: Config, resource_id: str) -> str:
    policy_name = f"{config.ecs_service}-scale-out"
    response = app_asg_client.put_scaling_policy(
        PolicyName=policy_name,
        ServiceNamespace="ecs",
        ResourceId=resource_id,
        ScalableDimension="ecs:service:DesiredCount",
        PolicyType="StepScaling",
        StepScalingPolicyConfiguration={
            "AdjustmentType": "ChangeInCapacity",
            "Cooldown": 60,
            "StepAdjustments": [
                {
                    "MetricIntervalLowerBound": 0.0,
                    "ScalingAdjustment": 2,
                }
            ],
        },
    )
    policy_arn = response.get("PolicyARN")
    if not isinstance(policy_arn, str) or not policy_arn:
        raise RuntimeError("Scale-out policy ARN missing from put_scaling_policy response")
    return policy_arn


def _put_scale_in_policy(app_asg_client: BaseClient, config: Config, resource_id: str) -> str:
    policy_name = f"{config.ecs_service}-scale-in"
    response = app_asg_client.put_scaling_policy(
        PolicyName=policy_name,
        ServiceNamespace="ecs",
        ResourceId=resource_id,
        ScalableDimension="ecs:service:DesiredCount",
        PolicyType="StepScaling",
        StepScalingPolicyConfiguration={
            "AdjustmentType": "ChangeInCapacity",
            "Cooldown": 120,
            "StepAdjustments": [
                {
                    "MetricIntervalUpperBound": 0.0,
                    "ScalingAdjustment": -1,
                }
            ],
        },
    )
    policy_arn = response.get("PolicyARN")
    if not isinstance(policy_arn, str) or not policy_arn:
        raise RuntimeError("Scale-in policy ARN missing from put_scaling_policy response")
    return policy_arn


def _put_scale_out_alarm(cloudwatch_client: BaseClient, config: Config, scale_out_policy_arn: str) -> None:
    alarm_name = f"{config.ecs_service}-queue-deep"
    cloudwatch_client.put_metric_alarm(
        AlarmName=alarm_name,
        AlarmDescription=f"Scale out {config.ecs_service} when SQS queue depth is high",
        Namespace="AWS/SQS",
        MetricName="ApproximateNumberOfMessagesVisible",
        Dimensions=[{"Name": "QueueName", "Value": config.sqs_queue_name}],
        Statistic="Average",
        Period=60,
        EvaluationPeriods=1,
        Threshold=float(config.scale_out_threshold),
        ComparisonOperator="GreaterThanOrEqualToThreshold",
        AlarmActions=[scale_out_policy_arn],
        TreatMissingData="notBreaching",
    )


def _put_scale_in_alarm(cloudwatch_client: BaseClient, config: Config, scale_in_policy_arn: str) -> None:
    alarm_name = f"{config.ecs_service}-queue-empty"
    cloudwatch_client.put_metric_alarm(
        AlarmName=alarm_name,
        AlarmDescription=f"Scale in {config.ecs_service} when SQS queue depth stays low",
        Namespace="AWS/SQS",
        MetricName="ApproximateNumberOfMessagesVisible",
        Dimensions=[{"Name": "QueueName", "Value": config.sqs_queue_name}],
        Statistic="Average",
        Period=60,
        EvaluationPeriods=3,
        Threshold=float(config.scale_in_threshold),
        ComparisonOperator="LessThanThreshold",
        AlarmActions=[scale_in_policy_arn],
        TreatMissingData="notBreaching",
    )


def _print_summary(config: Config) -> None:
    print("[OK] ECS auto-scaling configured")
    print(f"  Service:     {config.ecs_cluster}/{config.ecs_service}")
    print(f"  Min tasks:   {config.worker_min_tasks}  |  Max tasks: {config.worker_max_tasks}")
    print(f"  Scale-out:   queue depth >= {config.scale_out_threshold}  \u2192 +2 tasks")
    print(f"  Scale-in:    queue depth <  {config.scale_in_threshold}  (3 min sustained) \u2192 -1 task")
    print(f"  Metric:      {config.sqs_queue_name} queue depth")


def main() -> int:
    config = _load_config()
    _validate_config(config)

    app_asg_client = boto3.client("application-autoscaling", region_name=config.region)
    cloudwatch_client = boto3.client("cloudwatch", region_name=config.region)

    resource_id = _register_scalable_target(app_asg_client, config)
    scale_out_policy_arn = _put_scale_out_policy(app_asg_client, config, resource_id)
    scale_in_policy_arn = _put_scale_in_policy(app_asg_client, config, resource_id)

    _put_scale_out_alarm(cloudwatch_client, config, scale_out_policy_arn)
    _put_scale_in_alarm(cloudwatch_client, config, scale_in_policy_arn)

    _print_summary(config)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ClientError, ValueError, RuntimeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)


