## OIDC Gatekeeper Operator - a component of the Charmed Kubeflow distribution from Canonical

[![CharmHub Badge](https://charmhub.io/oidc-gatekeeper/badge.svg)](https://charmhub.io/oidc-gatekeeper)
[![Publish](https://github.com/canonical/oidc-gatekeeper-operator/actions/workflows/on_push.yaml/badge.svg)](https://github.com/canonical/oidc-gatekeeper-operator/actions/workflows/on_push.yaml)

This repository hosts the Kubernetes Python Operator for OIDC Gatekeeper
(see [CharmHub](https://charmhub.io/?q=oidc-gatekeeper)).

## Usage

The OIDC Gatekeeper Operator may be deployed using the Juju command line as follows
```bash
juju deploy oidc-gatekeeper --trust
juju deploy dex-auth --trust
juju config oidc-gatekeeper client-secret=<client-secret, optional>
juju integrate dex-auth:dex-oidc-config oidc-gatekeeper:dex-oidc-config
```

Upstream documentation can be found at https://github.com/arrikto/oidc-authservice

## Limitations

This charm has been designed around Charmed Kubeflow and it will not work as an OIDC client outside of a model where `dex-auth` and Charmed Kubeflow are deployed. There are currently no plans to change this behaviour.

## Looking for a fully supported platform for MLOps?

Canonical [Charmed Kubeflow](https://charmed-kubeflow.io) is a state of the art, fully supported MLOps platform that helps data scientists collaborate on AI innovation on any cloud from concept to production, offered by Canonical - the publishers of [Ubuntu](https://ubuntu.com).

<br/>

[![Kubeflow diagram](https://res.cloudinary.com/canonical/image/fetch/f_auto,q_auto,fl_sanitize,w_350,h_304/https://assets.ubuntu.com/v1/10400c98-Charmed-kubeflow-Topology-header.svg)](https://charmed-kubeflow.io)

<br/>

Charmed Kubeflow is free to use: the solution can be deployed in any environment without constraints, paywall or restricted features. Data labs and MLOps teams only need to train their data scientists and engineers once to work consistently and efficiently on any cloud – or on-premise.

Charmed Kubeflow offers a centralised, browser-based MLOps platform that runs on any conformant Kubernetes – offering enhanced productivity, improved governance and reducing the risks associated with shadow IT.

Learn more about deploying and using Charmed Kubeflow at [https://charmed-kubeflow.io](https://charmed-kubeflow.io).

### Key features
* Centralised, browser-based data science workspaces: **familiar experience**
* Multi user: **one environment for your whole data science team**
* NVIDIA GPU support: **accelerate deep learning model training**
* Apache Spark integration: **empower big data driven model training**
* Ideation to production: **automate model training & deployment**
* AutoML: **hyperparameter tuning, architecture search**
* Composable: **edge deployment configurations available**

### What’s included in Charmed Kubeflow 1.4
* LDAP Authentication
* Jupyter Notebooks
* Work with Python and R
* Support for TensorFlow, Pytorch, MXNet, XGBoost
* TFServing, Seldon-Core
* Katib (autoML)
* Apache Spark
* Argo Workflows
* Kubeflow Pipelines

### Why engineers and data scientists choose Charmed Kubeflow
* Maintenance: Charmed Kubeflow offers up to two years of maintenance on select releases
* Optional 24/7 support available, [contact us here](https://charmed-kubeflow.io/contact-us) for more information
* Optional dedicated fully managed service available, [contact us here](https://charmed-kubeflow.io/contact-us) for more information or [learn more about Canonical’s Managed Apps service](https://ubuntu.com/managed/apps).
* Portability: Charmed Kubeflow can be deployed on any conformant Kubernetes, on any cloud or on-premise

### Documentation
Please see the [official docs site](https://charmed-kubeflow.io/docs) for complete documentation of the Charmed Kubeflow distribution.

### Bugs and feature requests
If you find a bug in our operator or want to request a specific feature, please file a bug here:
[https://github.com/canonical/oidc-gatekeeper-operator/issues](https://github.com/canonical/oidc-gatekeeper-operator/issues)

### License
Charmed Kubeflow is free software, distributed under the [Apache Software License, version 2.0](https://github.com/canonical/oidc-gatekeeper-operator/blob/master/LICENSE).

### Contributing
Canonical welcomes contributions to Charmed Kubeflow. Please check out our [contributor agreement](https://ubuntu.com/legal/contributors) if you're interested in contributing to the distribution.

### Security
Security issues in Charmed Kubeflow can be reported through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File). Please do not file GitHub issues about security issues.
