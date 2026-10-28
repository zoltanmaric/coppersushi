terraform {
  required_version = ">= 1.5, < 2.0"
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "1.69.0"
    }
  }
}

# HCLOUD_TOKEN comes from the operator's environment, never a tfvars file.
provider "hcloud" {}

# Reuse an operator-managed public key; destroying this stack must not delete it.
data "hcloud_ssh_key" "operator" {
  name = var.ssh_key_name
}

resource "hcloud_primary_ip" "site" {
  for_each    = var.ip_names
  name        = each.value
  type        = each.key
  location    = var.location
  auto_delete = true

  lifecycle {
    prevent_destroy = true
  }
}

resource "hcloud_server" "site" {
  name        = var.server_name
  server_type = var.server_type
  image       = "ubuntu-24.04"
  location    = var.location
  backups     = var.backups
  labels      = var.labels
  ssh_keys    = [data.hcloud_ssh_key.operator.id]

  public_net {
    ipv4_enabled = true
    ipv4         = hcloud_primary_ip.site["ipv4"].id
    ipv6_enabled = true
    ipv6         = hcloud_primary_ip.site["ipv6"].id
  }

  lifecycle {
    prevent_destroy = true
    # Hetzner cannot read back the creation-time keys after importing a server.
    # Subsequent authorized_keys changes are an explicit operator operation.
    ignore_changes = [ssh_keys]
  }
}

output "ipv4_address" {
  value = hcloud_server.site.ipv4_address
}

output "server_id" {
  value = hcloud_server.site.id
}
