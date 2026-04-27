"""Charms dependencies for tests."""

from charmed_kubeflow_chisme.testing import CharmSpec

DEX_AUTH = CharmSpec(charm="dex-auth", channel="latest/edge", trust=True)
ISTIO_PILOT = CharmSpec(charm="istio-pilot", channel="latest/edge", trust=True)
JUPYTER_UI = CharmSpec(charm="jupyter-ui", channel="latest/edge", trust=True)
