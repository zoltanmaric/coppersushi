UV = uv run --locked
PLAYBOOK = $(UV) ansible-playbook -i "$(DEPLOY_PRIVATE)/inventory.yml" -e "@$(DEPLOY_PRIVATE)/site.yml"

.PHONY: setup test check configure restore
setup:
	uv sync --locked
	$(UV) ansible-galaxy collection install -r ansible/requirements.yml

test:
	terraform -chdir=terraform fmt -check
	terraform -chdir=terraform init -backend=false -input=false -lockfile=readonly
	terraform -chdir=terraform validate
	$(UV) ansible-playbook -i ansible/inventory.example.yml ansible/site.yml --syntax-check
	$(UV) ansible-playbook -i ansible/inventory.example.yml ansible/restore.yml --syntax-check
	$(UV) python -m unittest discover -s tests

check configure:
	@test -n "$(DEPLOY_PRIVATE)" || (echo 'Set DEPLOY_PRIVATE to your private inputs directory'; exit 1)
	$(PLAYBOOK) ansible/site.yml $(if $(filter check,$@),--check) $(if $(HOLD),-e ghost_start=false)

restore:
	@test -n "$(DEPLOY_PRIVATE)" || (echo 'Set DEPLOY_PRIVATE to your private inputs directory'; exit 1)
	$(PLAYBOOK) ansible/restore.yml -e 'restore_confirmation="$(CONFIRM)"'
