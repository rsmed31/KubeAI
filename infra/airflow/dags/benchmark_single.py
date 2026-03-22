"""Single benchmark DAG — manually triggered for one scenario + framework."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models.param import Param

from common import get_kubeai_api_url, get_postgres_conn_string

DEFAULT_ARGS = {
    "owner": "kubeai",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}


def _run_single_benchmark(
    scenario: str,
    framework: str,
    num_runs: int,
    run_id: str,
    **context,
) -> None:
    """Trigger a single benchmark run and record results."""
    import urllib.request

    api_url = get_kubeai_api_url()
    payload = json.dumps({
        "scenario": scenario,
        "framework": framework,
        "num_runs": num_runs,
        "run_id": run_id,
    }).encode()

    req = urllib.request.Request(
        f"{api_url}/api/benchmarks/run",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read())
            print(f"Benchmark complete: {result}")
    except Exception as exc:
        raise RuntimeError(f"Benchmark failed: {exc}") from exc


def _persist_run_metadata(run_id: str, scenario: str, framework: str, **context) -> None:
    """Write run metadata to PostgreSQL benchmark_runs table."""
    try:
        import psycopg2
        conn = psycopg2.connect(get_postgres_conn_string())
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO benchmark_runs (run_id, started_at, finished_at, status, scenario, framework_id)
            VALUES (%s, %s, %s, 'completed', %s, %s)
            ON CONFLICT (run_id) DO UPDATE
              SET finished_at = EXCLUDED.finished_at, status = EXCLUDED.status
            """,
            (run_id, context["data_interval_start"], datetime.utcnow(), scenario, framework),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:
        print(f"Warning: could not persist run metadata: {exc}")


with DAG(
    dag_id="kubeai_benchmark_single",
    description="Manually triggered benchmark: one scenario × one framework",
    default_args=DEFAULT_ARGS,
    schedule_interval=None,  # manual trigger only
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=3,
    tags=["kubeai", "benchmarks"],
    dagrun_timeout=timedelta(minutes=10),
    params={
        "scenario": Param(
            default="rag",
            type="string",
            description="Benchmark scenario: rag | codegen | research | data_analysis",
            enum=["rag", "codegen", "research", "data_analysis"],
        ),
        "framework": Param(
            default="litellm",
            type="string",
            description="Framework to benchmark: litellm | langchain | llamaindex | autogen | crewai",
            enum=["litellm", "langchain", "llamaindex", "autogen", "crewai"],
        ),
        "num_runs": Param(
            default=3,
            type="integer",
            description="Number of benchmark repetitions",
            minimum=1,
            maximum=10,
        ),
    },
) as dag:

    run_id = str(uuid.uuid4())

    run_benchmark = PythonOperator(
        task_id="run_benchmark",
        python_callable=_run_single_benchmark,
        op_kwargs={
            "scenario": "{{ params.scenario }}",
            "framework": "{{ params.framework }}",
            "num_runs": "{{ params.num_runs }}",
            "run_id": run_id,
        },
    )

    persist_metadata = PythonOperator(
        task_id="persist_metadata",
        python_callable=_persist_run_metadata,
        op_kwargs={
            "run_id": run_id,
            "scenario": "{{ params.scenario }}",
            "framework": "{{ params.framework }}",
        },
        trigger_rule="all_done",
    )

    run_benchmark >> persist_metadata
