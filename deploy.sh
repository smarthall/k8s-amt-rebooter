#!/bin/bash

kubectl create namespace amt-rebooter

kubectl -n amt-rebooter create configmap amt-rebooter-config --from-file=config=config.yaml --dry-run=client -o yaml | kubectl apply -f-

kubectl apply -f deployment.yaml
