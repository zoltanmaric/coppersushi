export ANSIBLE_COLLECTIONS_PATH := $(abspath ../../data/ansible/collections)
PLAYBOOK = ansible-playbook -i "$(DEPLOY_PRIVATE)/inventory.yml" -e "@$(DEPLOY_PRIVATE)/site.yml"

.PHONY: setup test check configure restore
setup:
	ansible-galaxy collection install -r ansible/requirements.yml -p "$(ANSIBLE_COLLECTIONS_PATH)"

test:
	terraform -chdir=terraform fmt -check
	terraform -chdir=terraform init -backend=false -input=false -lockfile=readonly
	terraform -chdir=terraform validate
	ansible-playbook -i ansible/inventory.example.yml ansible/site.yml --syntax-check
	ansible-playbook -i ansible/inventory.example.yml ansible/restore.yml --syntax-check
	python -m unittest discover -s tests

check configure:
	@test -n "$(DEPLOY_PRIVATE)" || (echo 'Set DEPLOY_PRIVATE to your private inputs directory'; exit 1)
	$(PLAYBOOK) ansible/site.yml $(if $(filter check,$@),--check) $(if $(HOLD),-e ghost_start=false)

restore:
	@test -n "$(DEPLOY_PRIVATE)" || (echo 'Set DEPLOY_PRIVATE to your private inputs directory'; exit 1)
	$(PLAYBOOK) ansible/restore.yml -e 'restore_confirmation="$(CONFIRM)"'
