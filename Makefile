.PHONY: all repo image

all: repo image

repo:
	cd repo && python -u build.py

image:
	sudo python -u build.py
