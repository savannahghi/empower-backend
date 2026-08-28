"""System Architecture Diagram."""
from diagrams import Cluster, Edge
from diagrams.aws.engagement import SimpleEmailServiceSes
from diagrams.gcp.analytics import BigQuery
from diagrams.gcp.database import SQL, Datastore
from diagrams.k8s.network import Ingress
from diagrams.onprem.client import Users
from diagrams.onprem.compute import Server
from diagrams.onprem.inmemory import Redis
from diagrams.onprem.monitoring import Grafana
from diagrams.onprem.queue import Celery, RabbitMQ
from diagrams.programming.framework import Django
from sphinx_diagrams import SphinxDiagram

with SphinxDiagram(
    title="System Architecture",
    graph_attr={"margin": "0", "pad": "0"},
):
    rabbitmq = RabbitMQ("RabbitMQ")
    redis = Redis("Redis Cache")

    with Cluster("Kubernetes Deployment"):
        ingress = Ingress("Kong Ingress")

        api = Django("API")
        ingress >> Edge(color="blue") << api
        api >> Edge(color="darkred") << redis
        api >> Edge(color="orange") >> rabbitmq

        workers = Celery("Celery Worker(s)")
        workers >> Edge(color="darkred") << redis
        rabbitmq >> Edge(color="orange") >> workers

    db = SQL("Postgres DB")
    api >> Edge(color="darkblue") << db
    workers >> Edge(color="darkblue") << db

    clients = Users("Users")
    clients >> Edge(color="black") << ingress

    authserver = Server("Authserver")
    api >> Edge(color="black") << authserver
    clients >> Edge(color="black") << authserver

    quintus = BigQuery("Quintus")
    db >> Edge(color="darkblue") >> quintus
    workers << Edge(color="darkblue") << quintus

    clinical = Datastore("Clinical Service")
    workers >> Edge(color="blue") >> clinical

    erp = Server("ERP")
    api >> Edge(color="purple") << erp

    grafana = Grafana("Grafana")
    api >> Edge(color="orange") >> grafana

    ses = SimpleEmailServiceSes("Amazon SES")
    api >> Edge(color="black") >> ses
