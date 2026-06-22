# main.py

import os
import time
import logging

from flask import Flask, jsonify
from google.cloud import bigquery
from google.cloud import monitoring_v3

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

PROJECT_ID = os.environ["PROJECT_ID"]

QUERY = """
SELECT
  ROUND(SUM(cost), 2) AS total_cost_7d
FROM
  `pgd-pgd-oiti-infra.billing_info.gcp_billing_export_resource_v1_01DF20_DD2658_424F64`
WHERE
  DATE(usage_start_time, 'Asia/Jakarta')
    >= DATE_SUB(CURRENT_DATE('Asia/Jakarta'), INTERVAL 7 DAY)
  AND service.description = 'BigQuery'
"""

METRIC_TYPE = "custom.googleapis.com/billing/bigquery_cost_7d"


@app.route("/", methods=["POST"])
def run_billing_check():
    try:
        total_cost = get_billing_cost()
        write_metric(total_cost)

        return jsonify(
            {
                "status": "success",
                "metric": METRIC_TYPE,
                "value": total_cost,
            }
        ), 200

    except Exception as exc:
        logging.exception(exc)

        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 500


def get_billing_cost():
    client = bigquery.Client(project=PROJECT_ID)

    query_job = client.query(QUERY)

    rows = list(query_job.result())

    if not rows:
        return 0.0

    value = rows[0].total_cost_7d

    if value is None:
        return 0.0

    logging.info(f"7-day cost: {value}")

    return float(value)


def write_metric(metric_value):
    client = monitoring_v3.MetricServiceClient()

    project_name = f"projects/{PROJECT_ID}"

    series = monitoring_v3.TimeSeries()

    series.metric.type = METRIC_TYPE

    series.resource.type = "global"

    point = series.points.add()

    point.value.double_value = metric_value

    point.interval.end_time.seconds = int(time.time())

    client.create_time_series(
        name=project_name,
        time_series=[series],
    )

    logging.info(
        f"Metric written successfully: {metric_value}"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
```
