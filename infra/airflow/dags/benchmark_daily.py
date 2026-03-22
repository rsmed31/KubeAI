"""Daily benchmark DAG — runs all 4 scenarios × all enabled frameworks."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from common import get_kubeai_api_url, get_postgres_conn_string

DEFAULT_ARGS = {
    "owner": "kubeai",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
}

SCENARIOS = ["rag", "codegen", "research", "data_analysis"]
FRAMEWORKS = ["litellm", "langchain", "llamaindex", "autogen", "crewai"]


def _get_enabled_frameworks(postgres_conn: str) -> list[str]:
    """Query framework_registry for enabled frameworks."""
    try:
        import psycopg2
        conn = psycopg2.connect(postgres_conn)
        cur = conn.cursor()
        cur.execute("SELECT framework_id FROM framework_registry WHERE enabled = TRUE")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [r[0] for r in rows] if rows else FRAMEWORKS
    except Exception:
        return FRAMEWORKS


def _run_benchmark(scenario: str, framework: str, **context) -> None:
    """Trigger a benchmark run via the KubeAI API."""
    import urllib.request

    api_url = get_kubeai_api_url()
    run_id = str(uuid.uuid4())
    payload = json.dumps({
        "scenario": scenario,
        "framework": framework,
        "num_runs": 3,
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
            print(f"Benchmark {scenario}/{framework}: {result}")
    except Exception as exc:
        raise RuntimeError(f"Benchmark failed for {scenario}/{framework}: {exc}") from exc


def _record_run_start(run_id: str, **context) -> None:
    """Record a benchmark batch run in PostgreSQL."""
    try:
        import psycopg2
        conn = psycopg2.connect(get_postgres_conn_string())
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO benchmark_runs (run_id, started_at, status, scenario, config_json)
            VALUES (%s, %s, 'running', 'daily_batch', '{}')
            ON CONFLICT (run_id) DO NOTHING
            """,
            (run_id, datetime.utcnow()),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:
        print(f"Warning: could not record run start: {exc}")


def _record_run_end(run_id: str, **context) -> None:
    """Mark benchmark batch run as finished in PostgreSQL."""
    try:
        import psycopg2
        conn = psycopg2.connect(get_postgres_conn_string())
        cur = conn.cursor()
        cur.execute(
            "UPDATE benchmark_runs SET finished_at = %s, status = 'completed' WHERE run_id = %s",
            (datetime.utcnow(), run_id),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:
        print(f"Warning: could not record run end: {exc}")


with DAG(
    dag_id="kubeai_benchmark_daily",
    description="Daily benchmark: all scenarios × all enabled frameworks",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 2 * * *",  # 02:00 UTC daily
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["kubeai", "benchmarks"],
    dagrun_timeout=timedelta(minutes=30),
) as dag:

    batch_run_id = str(uuid.uuid4())

    record_start = PythonOperator(
        task_id="record_run_start",
        python_callable=_record_run_start,
        op_kwargs={"run_id": batch_run_id},
    )

    # Build one task per (scenario, framework) pair
    benchmark_tasks = []
    for scenario in SCENARIOS:
        for framework in FRAMEWORKS:
            task = PythonOperator(
                task_id=f"bench_{scenario}_{framework}",
                python_callable=_run_benchmark,
                op_kwargs={"scenario": scenario, "framework": framework},
            )
            record_start >> task
            benchmark_tasks.append(task)

    record_end = PythonOperator(
        task_id="record_run_end",
        python_callable=_record_run_end,
        op_kwargs={"run_id": batch_run_id},
        trigger_rule="all_done",  # run even if some benchmarks failed
    )

    for task in benchmark_tasks:
        task >> record_end
