#!/usr/bin/env python
import sys, os, shutil, argparse
import memo


parser = argparse.ArgumentParser()
parser.add_argument('-t', '--time', default='4-00:00:00')
parser.add_argument('-n', '--ntasks', default=1, type=int)
parser.add_argument('-c', '--cpus-per-task', default=5, type=int)
parser.add_argument('--gres', default='gpu:titan-x:1')
parser.add_argument('--mem', default='40G')

kwargs, args = parser.parse_known_args()

dest = memo.setup_dest()
shutil.copy2(sys.argv[2], dest)
os.chdir(dest)

with open('run.sh', 'w') as f:
    f.write('#!/bin/sh\n')
    for k,v in kwargs.items():
        f.write(f'#SBATCH {k}={v}\n')
    f.write('\n')
    f.write('ssh -f -N -L 31001:localhost:31001 dicarlo5.mit.edu\n')
    f.write('"$@"\n')
args = ['sbatch', 'run.sh'] + args
memo.store(args=args, dest=dest)