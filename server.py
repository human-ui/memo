from __future__ import division, print_function, absolute_import

import json, time

import pandas

from bokeh.layouts import gridplot
from bokeh.plotting import figure, show, output_file

import flask
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
pandas.set_option('display.max_colwidth', -1)
sub = ''


@app.route('/', methods=['GET'])
def index():
    df = pandas.read_csv('index.csv', index_col=0, na_values='NaN', keep_default_na=False)
    df = df[df.show].drop('show', 1)
    df = df[::-1]
    table = df.to_html()
    table = format_table(table)
    return render_template('index.html', table=table)


@app.route('/wait-for-changes', methods=['POST'])
def wait_for_changes():
    global sub
    rows = request.form['data']
    sub = format_table(rows, return_rows=True)
    return 'ok'


# def get_stream():
#     global sub
#     if len(sub) > 0:
#         yield 'data: {}\n\n'.format(sub.replace('\n', ''))
#         sub = ''
#     # else:


# @app.route('/send-rows')
# def send_rows():
#     return flask.Response(get_stream(),  #jsonify(rows=rows),
#                           mimetype="text/event-stream")


def format_table(table, return_rows=False):
    table = table.replace('border="1" class="dataframe"', 'class="table"')
    if return_rows:
        start = table.find('<tbody>\n') + 9
        end = table.find('</tbody>')
        table = table[start:end]
    return table


@app.route('/', methods=['POST'])
def confirm_edit():
    row, col, value = json.loads(request.form['data'])
    # time.sleep(10)
    # print(row, col, value)
    df = pandas.read_csv('index.csv', index_col=0, na_values='NaN', keep_default_na=False)
    df.loc[int(row[1:]), col] = value
    df.to_csv('index.csv', encoding='utf-8')
    return 'ok'


@app.route('/remove-rows', methods=['POST'])
def remove_rows():
    index = json.loads(request.form['data'])
    index = int(index[1:])  # first character is x
    df = pandas.read_csv('index.csv', index_col=0, na_values='NaN', keep_default_na=False)
    df.loc[index, 'show'] = False
    df.to_csv('index.csv', encoding='utf-8')
    return 'ok'


if __name__ == '__main__':
    app.run(debug=True)
