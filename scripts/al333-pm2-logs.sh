#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"
pm2 logs baize-hub --lines 50 --nostream
