output "app_name" {
  value = juju_application.oidc_gatekeeper.name
}

output "peers" {
  value = {
    client_secret = "client-secret",
  }
}

output "provides" {
  value = {
    forward_auth     = "forward-auth",
    oidc_client      = "oidc-client",
    provide_cmr_mesh = "provide-cmr-mesh"
  }
}

output "requires" {
  value = {
    dex_oidc_config                     = "dex-oidc-config",
    ingress                             = "ingress",
    ingress_auth                        = "ingress-auth",
    istio_ingress_route_unauthenticated = "istio-ingress-route-unauthenticated",
    logging                             = "logging",
    require_cmr_mesh                    = "require-cmr-mesh",
    service_mesh                        = "service-mesh"
  }
}
