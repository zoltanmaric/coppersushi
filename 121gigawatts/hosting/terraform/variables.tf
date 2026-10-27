variable "server_name" {
  type        = string
  description = "Name of the permanent Ghost server."
}

variable "location" {
  type    = string
  default = "fsn1"
}

variable "ssh_key_name" {
  type        = string
  description = "Name of an existing Hetzner public SSH key."
}

variable "ip_names" {
  type        = map(string)
  description = "Names of the Ghost server's two primary IP resources."
  validation {
    condition     = toset(keys(var.ip_names)) == toset(["ipv4", "ipv6"])
    error_message = "Supply exactly ipv4 and ipv6 IP names."
  }
}

variable "server_type" {
  type        = string
  default     = "cx23"
  description = "Hetzner server type. Review any resize plan explicitly."
}

variable "backups" {
  type        = bool
  default     = true
  description = "Enable paid Hetzner daily backups."
}

variable "labels" {
  type        = map(string)
  default     = {}
  description = "Preserve existing resource labels when adopting a server."
}
