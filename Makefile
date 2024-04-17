.PHONY: all repo image

all: repo image

repo:
	cd repo && python build.py

image:
	sudo python build.py
