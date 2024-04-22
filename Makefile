.PHONY: all repo image

all: repo image

repo:
	rm -rf repo && git clone https://github.com/MolyuuOS/repo.git repo && cd repo && python -u build.py

image:
	sudo python -u build.py
