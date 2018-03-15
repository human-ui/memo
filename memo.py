#!/usr/bin/env python
import sys, os, time, shutil, argparse, subprocess, datetime, contextlib, pickle, inspect, socket
from collections import OrderedDict
# import requests
import numpy as np
import pandas
import seaborn as sns
# from watchdog.observers import Observer
# from watchdog.events import FileSystemEventHandler

ROOT = '/braintree/home/qbilius/dropbox/memo'
SCRATCH = '/braintree/home/qbilius/computed'
DATA_DIR = os.path.join(ROOT, 'store')
DBPATH = os.path.join(ROOT, 'index.csv')
pandas.set_option('display.max_colwidth', -1)


class PandasDB(object):

    def __init__(self):
        self.write = 'MEMO_DIR' in os.environ
        if self.write:
            self.path = os.path.join(os.environ['MEMO_DIR'])

    def __getitem__(self, key):
        return PandasColl(self.path, key)

    @contextlib.contextmanager
    def open_file(self, filename):
        f = open(os.path.join(self.path, filename), 'wb')
        yield f
        f.close()

    def savefig(self, filename, *args, **kwargs):
        sns.plt.savefig(os.path.join(self.path, filename), *args, **kwargs)

    def save_to_scratch(self, obj, filename):
        frame = inspect.getouterframes(inspect.currentframe())[1]
        caller = os.path.relpath(frame.filename, '/braintree/home/qbilius/dropbox')
        path = os.path.join(SCRATCH, os.path.splitext(caller)[0], filename)
        pickle.dump(obj, open(path, 'wb'))


class PandasColl(object):

    def __init__(self, path, name):
        self.path = os.path.join(path, name + '.csv')

    def append(self, new):
        try:
            df = pandas.read_csv(self.path, index_col=0, na_values='NaN', keep_default_na=False)
        except:
            df = new
        else:
            df = pandas.concat([df, new], ignore_index=True)
        df.to_csv(self.path, encoding='utf-8')

# def write_to_db(rec):
#     db = pandas.read_csv(DBPATH, index_col=0, na_values='')
#     db = db.append(rec, ignore_index=True)
#     db.to_csv(DBPATH, encoding='utf-8')


def setup_dest():
    db = pandas.read_csv(DBPATH, index_col=0, na_values='NaN', keep_default_na=False)
    os.environ['MEMO_IDX'] = f"{len(db):04d}"

    dest = os.path.join(DATA_DIR, os.environ['MEMO_IDX'])
    if not os.path.isdir(dest):
        os.makedirs(dest)
        os.environ['MEMO_DIR'] = dest + os.path.sep
    else:
        raise ValueError('{} already exists'.format(dest))
    print(f'memo id: {os.path.basename(dest)}, version: {version}')
    return dest


def store(args=None, dest=None):
    start = time.time()
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser()
    parser.add_argument('executable')
    parser.add_argument('script')
    parser.add_argument('-t', '--tag', default='')
    parser.add_argument('-d', '--description', default='')
    args, other = parser.parse_known_args(args)

    call_args = [args.executable, args.script] + other
    command = ' '.join(call_args)

    db = pandas.read_csv(DBPATH, index_col=0, na_values='NaN', keep_default_na=False)

    if command in db.command.values:
        version = db[db.command == command].version.max() + 1
    else:
        version = 1

    os.environ['MEMO_CMD_VERSION'] = str(version)
    # db.to_csv('/braintree/home/qbilius/dropbox/memo/index.csv', encoding='utf-8')
    # sys.exit()
    # dest = os.path.join(DATA_DIR, '{:04d}_{}'.format(len(db), timestamp))

    if dest is not None:
        dest = setup_dest()
    shutil.copy2(os.path.abspath(args.script), dest)

    rec = OrderedDict([('timestamp', timestamp),
                       ('command', command),
                       ('host', socket.gethostname()),
                       ('working dir', os.path.abspath(os.getcwd())),
                       ('duration', np.nan),
                       ('version', version),
                       ('tag', args.tag),
                       ('description', args.description),
                       ('outcome', ''),
                       ('show', True)
                       ])
    db = db.append(rec, ignore_index=True)
    idx = db.index[-1]

    db.to_csv(DBPATH, encoding='utf-8')

    # db = pandas.read_csv(DBPATH, index_col=0, na_values='')
    # requests.post('http://localhost:5000/wait-for-changes',
    #               data={'data': db.loc[db.index[-1:]].drop('show', 1).to_html()})

    p = subprocess.Popen(call_args)
    try:
        p.wait()
    except KeyboardInterrupt:
        p.terminate()

    dur = time.time() - start
    db = pandas.read_csv(DBPATH, index_col=0, na_values='')
    db.loc[idx, 'duration'] = int(dur)
    db.to_csv(DBPATH, encoding='utf-8')


if __name__ == '__main__':
    store()
