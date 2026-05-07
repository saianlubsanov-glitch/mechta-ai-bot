#!/bin/bash

while true
do
    echo "Starting Mechta.ai bot..."

    python -m bot.main

    echo "Bot crashed. Restarting in 5 seconds..."

    sleep 5
done
