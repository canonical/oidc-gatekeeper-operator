output "app_name" {
  value = juju_application.oidc_gatekeeper.name
}

output "provides" {
  value = {
    oidc_client = "oidc-client",
  }
}

output "requires" {
  value = {
    dex_oidc_config = "dex-oidc-config",
    ingress         = "ingress",
    ingress_auth    = "ingress-auth"
    logging         = "logging"
  }
}
