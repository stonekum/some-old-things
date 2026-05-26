#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 27 10:29:41 2025

@author: aston
"""

import requests
r = requests.get("https://api.deepseek.com/v1/chat/completions", timeout=10)
print(r.status_code)