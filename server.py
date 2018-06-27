import json

import pandas

# from bokeh.client import pull_session
# from bokeh.embed import server_session
from bokeh.embed import server_document, components

from flask import Flask, request, jsonify, render_template

import os, datetime

import numpy as np
import pandas

from bokeh.layouts import gridplot, widgetbox, row, column
from bokeh.plotting import figure, curdoc
from bokeh.models import ColumnDataSource, ColorBar, PrintfTickFormatter, HoverTool, Range1d, LinearColorMapper, FuncTickFormatter
from bokeh.models.glyphs import Image
from bokeh.palettes import Category10
from bokeh.models.widgets import Select, Button
import bokeh.resources


MEMO_PATH = '/braintree/data2/active/users/qbilius/memo/'


app = Flask(__name__)
pandas.set_option('display.max_colwidth', -1)
sub = ''


class Plot(object):

    def __init__(self, memo_id):
        self.memo_id = str(memo_id)
        self.nrecs = 0
        self.timestamp = datetime.datetime(datetime.MINYEAR, 1, 1)

        # memo_ids = sorted(os.listdir(MEMO_PATH))[::-1]
        # select_id = Select(title='memo_id', value=memo_ids[0], options=memo_ids)
        # select_id.on_change('value', self.change_id)

        # button_refresh = Button(label='Refresh', button_type='primary')
        # button_refresh.on_click(self.update_plots)
        # # self.widget_button_refresh = widgetbox(button_refresh)

        # self.widgetbox = {'id': select_id, 'refresh': button_refresh}
        # curdoc().add_root(row(list(self.widgetbox.values()), sizing_mode='fixed'))
        # curdoc().add_periodic_callback(self.update_widgets, 6000)
        # curdoc().title = 'tensorplay'

        agg = self.make_plots()
        self.update_plots(agg)

    # def change_id(self, attr, old, new):
    #     self.nrecs = 0
    #     self.timestamp = datetime.datetime(datetime.MINYEAR, 1, 1)
    #     agg = self.make_plots()
    #     self.update_plots(agg)

    # def update_widgets(self):
    #     self.widgetbox['id'].options = sorted(os.listdir(MEMO_PATH))[::-1]

    def get_data(self):
        df = []
        path = os.path.join(MEMO_PATH, self.memo_id, 'results.pkl')
        if not os.path.isfile(path):
            return df

        data = pandas.read_pickle(path)
        for rec in data[self.nrecs:]:
            common = list(rec['meta'].items())  # [('step', step)]
            # for key, value in rec.items():
            #     if not isinstance(value, (dict, list)) and key != '_id':
            #         common.append((key, value))
            for key, value in rec.items():
                if key != 'meta':
                    if isinstance(value, dict):
                        for k, v in value.items():
                            if isinstance(v, dict):
                                for ki, vi in v.items():
                                    df.append(dict(common + [('hue', ki), ('col', k), ('value', vi)]))
                            # elif isinstance(v, bytes):  # image
                            #     import ipdb; ipdb.set_trace()

                            else:
                                df.append(dict(common + [('hue', key), ('col', k), ('value', v)]))
                    elif isinstance(value, list):
                        r = {'hue': key,
                            'col': 'dur',
                            'value': value[0]['dur']}
                        r.update(common)
                        tmp = [r]
                        other_keys = set(value[0].keys()) - set(['kind', 'dur', 'col', 'value'])
                        for val in value:
                            if len(other_keys) > 0:
                                r = {'hue': ' '.join([str(val[o]) for o in other_keys if not isinstance(val[o], float)]),
                                    'col': val['target'],
                                    'value': val['value']}
                            else:
                                r = val.copy()
                            r.update(common)
                            tmp.append(r)
                        df.extend(tmp)
        df = pandas.DataFrame(df)
        self.nrecs = len(data)
        return df

    def get_agg(self):
        df = self.get_data()

        if len(df) > 0:
            sel = df.value.apply(lambda x: isinstance(x, bytes))
            sdf = df[~sel]
            sdf.value = sdf.value.astype(float)
            if 'group' in df:
                agg = sdf.groupby(['col', 'hue', 'group', 'step']).value.mean()
            else:
                agg = sdf.groupby(['col', 'hue', 'step']).value.mean()
            # ims = df[sel & (df[sel].step == df[sel].step.max())].value.values
            ims = None
        else:
            agg = None
            ims = None
        return agg, ims

    def make_plots(self):
        agg, ims = self.get_agg()
        plots = []
        sources = {}

        if ims is not None:
            p = figure(plot_height=300, plot_width=300, title='images',
                        x_range=[0,256], y_range=[0,256],
                        tools=['save', 'ywheel_zoom', 'pan', 'reset'],
                        toolbar_location='above', min_border_left=80)
            sources['ims'] = ColumnDataSource({'data': [], 'width': [], 'height': [],
                                            'x': [], 'y': []})
            p.image(image='data', x='x', y='y', dw='width', dh='height', source=sources['ims'],palette='Greys9')
            plots.append(p)

        for col in agg.index.levels[0]:
            sources[col] = {}

            hover = HoverTool(tooltips=[('step', '@step'), (col, '@{{{}}}'.format(col))])
            p = figure(plot_height=300, plot_width=400, title=col,
                       tools=['save', 'ywheel_zoom', 'pan', 'reset'],
                       toolbar_location='above', min_border_left=80)
            p.add_tools(hover)
            p.xaxis.axis_label = 'step'
            p.yaxis.axis_label = col
            p.xaxis[0].formatter = PrintfTickFormatter(format='%d')

            uq_hue = agg.loc[col].reset_index().hue.unique()
            threshold = 10  #2 if self.widgetbox['port'].value == '27017' else 10

            if len(uq_hue) > threshold:
                sources[col] = ColumnDataSource({'data': [],
                                                 'width': [], 'height': [],
                                                 'x': [], 'y': []})
                mapper = LinearColorMapper(palette='Inferno256', low=0, high=1)
                p.image(image='data', x='x', y='y',
                        dw='width', dh='height',
                        source=sources[col], color_mapper=mapper)

                colorbar = ColorBar(color_mapper=mapper, location=(0,0))
                p.add_layout(colorbar, 'right')
                p.x_range = Range1d(0,0)
                p.y_range = Range1d(0,0)

            else:
                for i, hue in enumerate(uq_hue):
                    sources[col][hue] = ColumnDataSource({'step': [], col:[]})
                    p.line(x='step', y=col, color=Category10[10][i], legend=str(hue),
                        source=sources[col][hue])
                p.legend.location = 'bottom_left'
                p.legend.background_fill_alpha = 0

            plots.append(p)
        # import ipdb; ipdb.set_trace()
        self.plots = {col: plot for col, plot in zip(agg.index.levels[0], plots)}
        # layout = gridplot(plots, ncols=3, merge_tools=False)
        # if hasattr(self, 'layout'):
        #     self.layout.children = layout.children
        # else:
        # self.layout = layout
        # curdoc().add_root(self.layout)
        # curdoc().add_periodic_callback(self.update_plots, 600)
        self.sources = sources
        return agg, ims

    def update_plots(self, agg=None):
        if agg is None:
            agg, ims = self.get_agg()
        else:
            agg, ims = agg
        if agg is not None:
            for col in self.sources:
                if not isinstance(self.sources[col], dict):
                    try:

                        data = agg.loc[col, :, 0].unstack()

                        p = self.plots[col]
                        mapper = p.select_one(LinearColorMapper)
                        if self.nrecs == 0:
                            mapper.low = np.nanmin(data.values)
                            mapper.high = np.nanmax(data.values)
                        else:
                            if np.nanmin(data.values) < mapper.low:
                                mapper.update(low=np.nanmin(data.values))
                            if np.nanmax(data.values) > mapper.high:
                                mapper.update(high=np.nanmax(data.values))

                        p.x_range.end += data.shape[1]
                        if self.nrecs == 0:
                            p.y_range.end = data.shape[0]

                        # import ipdb; ipdb.set_trace()
                        p.yaxis.formatter = FuncTickFormatter(code="""
                                                        var labels = %s;
                                                        return labels[tick];
                                                    """ % data.loc[col, 0].reset_index().hue.to_dict())


                        new_data = {'data': [data.values],
                                    'width': [p.x_range.end],
                                    'height': [data.shape[0]],
                                    'x': [0],
                                    'y': [0]}

                        self.sources[col].stream(new_data)
                    except:
                        pass
                else:
                    for hue in self.sources[col]:
                        try:
                            if 'group' in agg.loc[(col, hue)].index.names:
                                new_data = {'step': agg.loc[(col, hue, 0)].index,
                                            col: agg.loc[(col, hue, 0)]}
                                # import ipdb; ipdb.set_trace()
                                self.sources[col][hue].stream(new_data)
                            else:
                                new_data = {'step': agg.loc[(col, hue)].index,
                                            col: agg.loc[(col, hue)]}
                                # import ipdb; ipdb.set_trace()
                                self.sources[col][hue].stream(new_data)
                        except:  # because not all updates have all cols
                            # import ipdb; ipdb.set_trace()
                            pass
            # self.nrecs = len(agg)

        if ims is not None:
            d = int(np.ceil(np.sqrt(len(ims))))
            # import ipdb; ipdb.set_trace()
            x, y = np.meshgrid(256 * np.arange(d), 256 * np.arange(d))
            new_data = {'data': [np.fromstring(im, np.float32).reshape((256,256,3)) for im in ims],
                        'width': [256] * len(ims),
                        'height': [256] * len(ims),
                        'x': x.ravel(),
                        'y': y.ravel()}
            new_data = {'data': [np.fromstring(ims[0], np.float32).reshape((256,256,3))],
                        'width': [256],
                        'height': [256],
                        'x': [0],
                        'y': [0]}
            # import matplotlib.pyplot as plt
            # # import ipdb; ipdb.set_trace()
            # plt.imshow(new_data['data'][0])
            # plt.show()
            self.sources['ims'].stream(new_data)# = new_data


@app.route('/', methods=['GET'])
def index():
    df = pandas.read_csv('index.csv', index_col=0, na_values='NaN', keep_default_na=False)
    df = df[df.show].drop('show', 1)
    df = df[::-1]
    df = df[:50]
    table = df.to_html()
    table = format_table(table)
    return render_template('index.html', table=table, resources=bokeh.resources.CDN.render())


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


@app.route('/popup', methods=['POST'])
def popup():
    row = json.loads(request.form['data'])
    pp = Plot(row[1:])
    script, div = components(pp.plots)
    return script + ''.join(div.values())
    # script = server_document('http://localhost:5006/plot2')
    # return render_template('index.html', script=script, div=''.join(div.values()))

    # with pull_session(url="http://localhost:5006/plot2") as session:
    #     # update or customize that session
    #     session.document.roots[0].children[1].title.text = "Special Sliders For A Specific User!"

    #     # generate a script to load the customized session
    #     script = server_session(session_id=session.id, url='http://localhost:5006/plot2')

    #     # use the script in the rendered page
    #     return render_template("embed.html", script=script, template="Flask")


if __name__ == '__main__':
    app.run(port=5000, debug=True)
