import logging
import os
import time

from flask import Flask, jsonify, request
from google.cloud import bigquery
from google.cloud import monitoring_v3
from google.protobuf.timestamp_pb2 import Timestamp

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

PROJECT_ID = os.getenv("PROJECT_ID", "pgd-pgd-oiti-infra")

QUERY = """
SELECT
  COALESCE(ROUND(SUM(cost), 2), 0) AS total_cost_7d
FROM
  `pgd-pgd-oiti-infra.billing_info.gcp_billing_export_resource_v1_01DF20_DD2658_424F64`
WHERE
  DATE(usage_start_time, 'Asia/Jakarta')
    >= DATE_SUB(CURRENT_DATE('Asia/Jakarta'), INTERVAL 7 DAY)
  AND service.description = 'BigQuery'
"""

METRIC_TYPE = "custom.googleapis.com/billing/bigquery_cost_7d"


@app.route("/healthz", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy"}), 200


@app.route("/", methods=["POST"])
def run_billing_check():
    try:
        request_json = request.get_json(silent=True) or {}
        logging.info(f"Request received: {request_json}")

        total_cost = get_billing_cost()

        write_metric(total_cost)

        return jsonify(
            {
                "status": "success",
                "project_id": PROJECT_ID,
                "metric": METRIC_TYPE,
                "value": total_cost,
            }
        ), 200

    except Exception as exc:
        logging.exception("Failed to process billing metric")

        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 500


def get_billing_cost():
    client = bigquery.Client(project=PROJECT_ID)

    logging.info("Executing BigQuery query")

    query_job = client.query(QUERY)

    rows = list(query_job.result())

    if not rows:
        logging.warning("No rows returned from BigQuery")

        return 0.0

    total_cost = float(rows[0].total_cost_7d or 0)

    logging.info(f"7-day BigQuery cost: {total_cost}")

    return total_cost


def write_metric(metric_value):
    client = monitoring_v3.MetricServiceClient()

    project_name = f"projects/{PROJECT_ID}"

    series = monitoring_v3.TimeSeries()

    # Custom metric
    series.metric.type = METRIC_TYPE

    # Optional metric labels
    series.metric.labels["service"] = "bigquery"

    # Required monitored resource
    series.resource.type = "global"
    series.resource.labels["project_id"] = PROJECT_ID

    now = Timestamp()
    now.FromSeconds(int(time.time()))

    interval = monitoring_v3.TimeInterval(
        end_time=now
    )

    point = monitoring_v3.Point(
        interval=interval,
        value=monitoring_v3.TypedValue(
            double_value=metric_value
        ),
    )

    series.points.append(point)

    logging.info(
        f"Writing metric: {METRIC_TYPE}={metric_value}"
    )

    client.create_time_series(
        name=project_name,
        time_series=[series],
    )

    logging.info(
        f"Successfully wrote metric "
        f"{METRIC_TYPE}={metric_value}"
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
    )