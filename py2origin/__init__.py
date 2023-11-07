"""Convert matplotlib figure into origin.

Useful documentation sources:
https://www.originlab.com/doc/COM/Classes/ApplicationSI
    Description of classes and functions available through COM server
https://www.originlab.com/doc/OriginC/ref/
    Some overlap with above, but at times provides more specific examples
    This lists a number of the commands for OriginC
    These can often be directly translated to python commands
https://www.originlab.com/doc/LabTalk/ref/
    LabTalk commands often allow more specific/particular operations
    e.g. changing axis scales, font sizes, etc.
"""

import os
import re
import time
import warnings

import matplotlib
import matplotlib.colors as colors
import matplotlib.pyplot as plt
import numpy as np
import OriginExt
import originpro as op
import win32com.client

__version__ = "0.1.2"

# Ideas for improvements:
# - Compile line data (labels, format, color) into df
#   then use df to sort and group lines in origin
# - support for subplots / multiple layers
# - support for double y or double x axes
# - support for errorbars


class SkipSave():
    pass


def set_axis_scale(gl, axis='x', scale='linear'):
    # axis = 'x' or 'y'
    # scale = 'linear' or 'log'
    # graph_layer is origin graph_layer object
    # Axis label number format:
    # 1 = decimal without commas, 2 = scientific,
    # 3 = engineering, and 4 = decimal with commas (for date).
    # https://www.originlab.com/doc/LabTalk/ref/Layer-Axis-Label-obj
    if scale == 'linear':
        gl.lt_exec('layer.' + axis + '.type = 0;')
        # Change number format to decimal
        gl.lt_exec('layer.' + axis + '.label.numFormat=1')
    elif scale == 'log':
        gl.lt_exec('layer.' + axis + '.type = 2;')
        # Change tick label number type to scientific
        gl.lt_exec('layer.' + axis + '.label.numFormat=2')
    return


def get_graphpages(origin):
    graphpages = []
    graphnames = []
    for gp in origin.GraphPages:
        graphpages.append(gp)
        graphnames.append(gp.Name)
    return graphpages, graphnames


def get_workbooks(origin):
    workbooks = []
    workbook_names = []
    for wb in origin.WorksheetPages:
        workbooks.append(wb)
        workbook_names.append(wb.Name)
    return workbooks, workbook_names


def get_all_sheets(origin):
    worksheets = []
    worksheet_names = []
    for wb in origin.WorksheetPages:
        for ws in wb.Layers:
            worksheets.append(ws)
            worksheet_names.append(ws.Name)
    print('Found ' + str(len(worksheets)) + ' worksheets')
    return worksheets, worksheet_names


def get_sheets_from_book(origin, workbooks):
    # origin is the active origin session
    # workbooks is a COM object, string of the workbook name,
    # a list of COM objects, or a list of strings
    # This can be used to get a list of worksheets which are then passed to
    # createGraph_multiwks to create graphs
    worksheets = []
    if isinstance(workbooks, str) or isinstance(
            workbooks, win32com.client.CDispatch):
        wb_list = [workbooks]
    elif isinstance(workbooks, list):
        wb_list = workbooks
    else:
        print('wrong type of workbooks provided. Must be COM object, string or list')
        return
    for wb in wb_list:
        if isinstance(wb, win32com.client.CDispatch):
            # If a COM object, this is already OK
            pass
        elif isinstance(wb, str):
            # If a string, get workbook from name
            wb = origin.WorksheetPages(workbook_name)
        else:
            print('wrong type of workbook provided. Must be COM object or string')
        if wb is None:
            print('workbook does not exist. Check if name is correct')
        else:
            for ws in wb.Layers:
                worksheets.append(ws)
    print('Found ' + str(len(worksheets)) + ' worksheets')
    return worksheets


def connect_to_origin():
    # Connect to Origin client
    # OriginExt.Application() forces a new connection
    origin = OriginExt.ApplicationSI()
    origin.Visible = origin.MAINWND_SHOW  # Make session visible
    # Session can be later closed using origin.Exit()
    # Close previous project and make a new one
    # origin.NewProject()
    # Wait for origin to compile
    # https://www.originlab.com/doc/LabTalk/ref/Second-cmd#-poc.3B_Pause_up_to_the_specified_number_of_seconds_to_wait_for_Origin_OC_startup_compiling_to_finish
    origin.Execute("sec -poc 3.5")
    time.sleep(3.5)
    return origin


def get_origin_version(origin):
    # Get origin version
    # Origin 2015 9.2xn
    # Origin 2016 9.3xn
    # Origin 2017 9.4xn
    # Origin 2018 >= 9.50n and < 9.55n
    # Origin 2018b >= 9.55n
    # Origin 2019 >= 9.60n and < 9.65n (Fall 2019)
    # Origin 2019b >= 9.65n (Spring 2020)
    return origin.GetLTVar("@V")


def save_project(origin, project_name, full_path):
    # File ending is automatically added by origin
    project_name = project_name.replace('.opju', '').replace('.opj', '')
    origin.Execute("save " + os.path.join(full_path, project_name))


def matplotlib_to_origin(
        fig, ax,
        origin=None,
        folder_name=None,
        workbook_name='Book',
        worksheet_name='Sheet',
        graph_name='Graph',
        template_name='LINE.otp',
        template_path=os.path.join(__path__[0], "OriginTemplates")):
    '''
    Inputs:
    fig = matplotli b figure object
    ax = matplotlib axis object
    template = origin template name for desired plot, if exists
    templatePath = path on local computer to template folder
    origin = origin session, which is returned from previous calls to this program
             if passed, a new session will not be created, and graph will be added to
             current session
    '''
    # See https://docs.originlab.com/originpro/index.html
    # If no origin session has been passed, start a new one

    if origin == SkipSave:
        return origin

    op.attach()
    op.set_show()

    if folder_name is not None:
        # op.pe.cd("/")
        op.pe.mkdir(folder_name, chk=True)
        op.pe.cd(folder_name)

    # Create a workbook page
    wkb = op.new_book('w', workbook_name)
    wks = wkb.add_sheet(worksheet_name)

    # Make graph page
    template = os.path.join(template_path, template_name)  # Pick template
    # Make a graph with the template
    gp = op.new_graph(graph_name, template)
    gl = gp[0] if gp is not None else None

    # line blongs to container
    contaienr_childeren = [
        c for container in ax.containers for c in container.get_children()]

    # extract lines
    lines = [(line, None) for line in ax.lines if line not in contaienr_childeren] + \
            [(container.lines[0], container) for container in ax.containers]

    next_idx = 0
    for line, container in lines:
        # extract data
        xdata = line.get_xdata()
        if hasattr(xdata, "value"):
            xdata = xdata.to(ax.xaxis.get_units()).value
        ydata = line.get_ydata()
        if hasattr(ydata, "value"):
            ydata = ydata.to(ax.yaxis.get_units()).value
        yerrdata = None

        if container is None:
            label = line.get_label() if line.get_label()[0] != "_" else ''
            label = re.sub(r"\$(.+?)\$", r"\\q(\1)", label)

            # Indices for x and y columns
            x_col_idx = next_idx
            y_col_idx = next_idx + 1
            yerr_col_idx = -1
            next_idx += 2

        elif isinstance(container, matplotlib.container.ErrorbarContainer):
            label = container.get_label() if container.get_label()[0] != "_" else ''
            label = re.sub(r"\$(.+?)\$", r"\\q(\1)", label)

            line = container.lines[0]
            # Indices for x, y and yerr columns
            x_col_idx = next_idx
            y_col_idx = next_idx + 1
            yerr_col_idx = next_idx + 2
            next_idx += 3

            yerrldata = container.lines[1][0].get_ydata()
            yerrudata = container.lines[1][1].get_ydata()
            yerrdata = (yerrudata - yerrldata) / 2
            if hasattr(yerrdata, "value"):
                yerrdata = yerrdata.to(ax.yaxis.get_units()).value

        else:
            warnings.warn(f"unknown container {container}")
            continue

        # Add data to sheet
        wks.from_list(
            x_col_idx,
            np.float64(xdata).tolist(),
            'X',
            units='Unit',
            comments='',
            axis='X')
        wks.from_list(
            y_col_idx,
            np.float64(ydata).tolist(),
            'Y',
            units='Unit',
            comments=label,
            axis='Y')
        if yerrdata is not None:
            wks.from_list(
                yerr_col_idx,
                np.float64(yerrdata).tolist(),
                'Yerr',
                units='Unit',
                comments='',
                axis='E')

        # Add data plot to graph layer
        # 200 -- line
        # 201 -- symbol
        # 202 -- symbol+line
        # Symbols
        # https://www.originlab.com/doc/LabTalk/ref/List-of-Symbol-Shapes
        # https://www.originlab.com/doc/LabTalk/ref/Options_for_Symbols
        # 0 = no symbol, 1 = square, 2 = circle, 3 = up triangle, 4 = down triangle,
        # 5 = diamond, 6 = cross (+), 7 = cross (x), 8 = star (*), 9 = bar (-), 10 = bar (|),
        # 11 = number, 12 = LETTER, 13 = letter, 14 = right arrow, 15 = left triangle,
        # 16 = right triangle, 17 = hexagon, 18 = star, 19 = pentagon, 20 = sphere
        # Symbol interior
        # 0 = no symbol, 1 = solid, 2 = open, 3 = dot center, 4 = hollow, 5 = + center,
        # 6 = x center, 7 = - center, 8 = | center, 9 = half up, 10 = half right,
        # 11 = half down, 12 = half left
        # https://matplotlib.org/api/markers_api.html
        mpl_sym_conv = {'s': '1', 'o': '2', '^': '3', 'v': '4', 'D': '5', '+': '6', 'x': '7',
                        '*': '8', '_': '9', '|': '10', 'h': '17', 'p': '19'}
        mpl_line_conv = {'-': '0', '--': '1', ':': '2', '-.': '3'}

        # p.symbol_kind = 2

        # 'l'(Line Plot) 's'(Scatter Plot) 'y' (Line Symbols) 'c' (Column) '?' auto(template)
        # Line
        if plt.getp(line, 'marker') == 'None':
            p = gl.add_plot(
                wks,
                y_col_idx,
                x_col_idx,
                type="l",
                colyerr=yerr_col_idx)
            lc = colors.to_hex(plt.getp(line, 'color'))
            # Set line color and line width
            p.set_cmd(
                '-d ' + mpl_line_conv.get(plt.getp(line, 'linestyle'), '0'), # linestyle
                '-cl color(' + lc + ')',
                '-w 500*' + str(plt.getp(line, 'linewidth'))  # line width
            )

        # Symbol
        elif plt.getp(line, 'linestyle') == 'None':
            p = gl.add_plot(
                wks,
                y_col_idx,
                x_col_idx,
                type="s",
                colyerr=yerr_col_idx)
            # Set symbol size, edge color, face color
            mec = colors.to_hex(plt.getp(line, 'mec'))
            mfc = colors.to_hex(plt.getp(line, 'mfc'))
            p.set_cmd(
                '-k ' + mpl_sym_conv.get(plt.getp(line, 'marker'), '0'),  # symbol type
                '-kf 2',  # symbol interior
                '-z ' + str(plt.getp(line, 'ms')),  # symbol size
                '-c color(' + mec + ')',  # face color
                '-csf color(' + mfc + ')',  # edge color
                '-kh 10*' + str(plt.getp(line, 'mew'))  # edge width
            )

        # Line+Symbol
        else:
            p = gl.add_plot(
                wks,
                y_col_idx,
                x_col_idx,
                type="y",
                colyerr=yerr_col_idx)
            # Set symbol size, edge color, face color
            lc = colors.to_hex(plt.getp(line, 'color'))
            mec = colors.to_hex(plt.getp(line, 'mec'))
            mfc = colors.to_hex(plt.getp(line, 'mfc'))
            p.set_cmd(
                # symbol type
                '-k ' + mpl_sym_conv[plt.getp(line, 'marker')],
                '-kf 2',  # symbol interior
                '-z ' + str(plt.getp(line, 'ms')),  # symbol size
                '-c color(' + mec + ')',  # edge color
                '-csf color(' + mfc + ')',  # face color
                # edge width
                '-kh 10*' + str(plt.getp(line, 'mew')),
                '-cl color(' + lc + ')',  # line color
                '-w 500*' + str(plt.getp(line, 'linewidth')),  # line width
            )

        gl.rescale()

    # For labtalk documentation of graph formatting, see:
    # https://www.originlab.com/doc/LabTalk/guide/Formatting-Graphs
    # https://www.originlab.com/doc/LabTalk/ref/Layer-Axis-Label-obj
    # For matplotlib documentation, see:
    # https://matplotlib.org/api/axes_api.html
    # Get figure dimensions
    # Set figure dimensions
    # Get axes ranges
    x_axis_range = ax.get_xlim()
    y_axis_range = ax.get_ylim()
    # Get axes scale types
    x_axis_scale = ax.get_xscale()
    y_axis_scale = ax.get_yscale()
    # Get axes labels
    x_axis_label = ax.get_xlabel()
    x_axis_label = re.sub(r"\$(.+?)\$", r"\\q(\1)", x_axis_label)
    y_axis_label = ax.get_ylabel()
    y_axis_label = re.sub(r"\$(.+?)\$", r"\\q(\1)", y_axis_label)
    title = ax.get_title()
    # Set axes titles (xb for bottom axis, yl for left y-axis, etc.)
    gl.axis("x").title = x_axis_label
    gl.axis("y").title = y_axis_label
    # Set fontsizes
    # graph_layer.Execute('layer.x.label.pt = 12;')
    # graph_layer.Execute('layer.y.label.pt = 12;')
    # graph_layer.Execute('xb.fsize = 16;')
    # graph_layer.Execute('yl.fsize = 16;')

    # Set axis scales
    set_axis_scale(gl, axis='x', scale=x_axis_scale)
    set_axis_scale(gl, axis='y', scale=y_axis_scale)
    # Set axis ranges
    gl.set_xlim(*x_axis_range)
    gl.set_ylim(*y_axis_range)

    # Set page dimensions based on figure size
    # Units 1 = % page, 2 = inches, 3 = cm, 4 = mm, 5 = pixel, 6 = points, and
    # 7 = % of linked layer.
    figure_size_inches = fig.get_size_inches()
    gl.set_int("unit", 2)
    gl.set_float("width", figure_size_inches[0])
    gl.set_float("height", figure_size_inches[1])
    op.lt_exec("pfit2l margin:=tight;")
    # graph_page.SetWidth(figure_size_inches[0])
    # graph_page.SetHeight(figure_size_inches[1])
    # graph_page.Execute('page.width= page.resx*'+str(figure_size_inches[0])+'; '+
    # 'page.height= page.resy*'+str(figure_size_inches[1])+';')
    # Units 1 = % page, 2 = inches, 3 = cm, 4 = mm, 5 = pixel, 6 = points, and 7 = % of linked layer.
    # graph_layer.Execute('layer.unit=2; ' +
    # 'layer.width='+str(figure_size_inches[0])+'; '+
    # 'layer.height='+str(figure_size_inches[1])+';')
    # Group each column (This allows colors to be automatically incremented
    # and a single legend entry to be created for all the data sets with
    # the same legend entry)
    # graph_layer.Execute('layer -g ' + str(group_start_idx) + ' '  + str(group_end_idx) + ';')
    # graph_layer.Execute('Rescale')
    op.lt_exec('legend -r')  # re-construct legend
    title = ax.get_legend().get_title().get_text()
    if title != "":
        title = re.sub(r"\$(.+?)\$", r"\\q(\1)", title)
        legend_text = op.get_lt_str("legend.text")
        op.lt_exec(f"legend.text$={title}\n{legend_text};")

    return op


def numpy_to_origin(
        data_array, column_axis=0, types=None,
        long_names=None, comments=None, units=None,
        user_defined=None, origin=None,
        worksheet_name='Sheet', workbook_name='Book'):
    '''
    Sends 2d numpy array to originlab worksheet
    Inputs:
    data_array = numpy array object
    column_axis = integer (0 or 1) for axis to interpret as worksheet columns
    long_names,comments,units = lists for header rows, length = # of columns
    user_defined = list of (key,value) tuples for metadata for a sheet
        e.g. [('Test Date','2019-01-01'),('Device Label','A12')]
    origin = origin session, which is returned from previous calls to this program
             if passed, a new session will not be created, and graph will be added to
             current session
    origin_version = 2016 other year, right now >2016 handles DataRange differently
    types = column types, either 'x','y','x_err','y_err','z','label', or 'ignore'
    '''
    # If no origin session has been passed, start a new one
    if origin is None:
        origin = connect_to_origin()
    origin_version = get_origin_version(origin)
    # Check if workbook exists. If not create a new workbook page with this
    # name
    layer_idx = None
    if origin.WorksheetPages(workbook_name) is None:
        workbook_name = origin.CreatePage(
            2, workbook_name, 'Origin')  # 2 for workbook
        # Use Sheet1 if workbook is newly made
        layer_idx = 0
    # get workbook instance from name
    wb = origin.WorksheetPages(workbook_name)
    if layer_idx is None:
        wb.Layers.Add()  # Add a worksheet
        # then find the last worksheet to modify (to avoid overwriting other
        # data)
        layer_idx = wb.Layers.Count - 1
    ws = wb.Layers(layer_idx)  # Get worksheet instance, index starts at 0.
    ws.Name = worksheet_name  # Set worksheet name
    # For now, assume only x and y data for each line (ignore error data)
    # Set number of columns in worksheet
    ws.Cols = data_array.shape[column_axis]
    # Change column Units, Long Name, or Comments]
    for col_idx in range(0, data_array.shape[column_axis]):
        col = ws.Columns(col_idx)  # Get column instance, index starts at 0
        # Go through, check that each value exists and add to worksheet
        if (long_names is not None) and (len(long_names) > col_idx):
            col.LongName = long_names[col_idx]
        if (units is not None) and (len(units) > col_idx):
            col.Units = units[col_idx]
        if (comments is not None) and (len(comments) > col_idx):
            col.Comments = comments[col_idx]
        if not (types is None) and (len(types) > col_idx):
            type_str_to_int = {
                'x': 3,
                'y': 0,
                'x_err': 6,
                'y_err': 2,
                'label': 4,
                'z': 5,
                'ignore': 1}
            # Set column data type to (0 = Y, 1 = disregard, 2 = Y Error, 3 = X, 4 = Label, 5 = Z, and 6 = X Error.)
            # documentation here is off by one
            # https://www.originlab.com/doc/LabTalk/ref/Wks-Col-obj
            col.Type = type_str_to_int[types[col_idx].lower()]
        # Check dimensionality off array.
        # If one dimensional, each element is assumed to be a column
        # If two dimensional, check
        # other dimensions are not supported.
        if data_array.ndim == 2:
            if column_axis == 0:
                origin.PutWorksheet('[' + wb.Name + ']' + ws.Name, np.float64(
                    data_array[col_idx, :]).tolist(), 0, col_idx)  # start row, start col
            elif column_axis == 1:
                origin.PutWorksheet('[' + wb.Name + ']' + ws.Name, np.float64(
                    data_array[:, col_idx]).tolist(), 0, col_idx)  # start row, start col
        elif data_array.ndim == 1:
            origin.PutWorksheet(
                '[' + wb.Name + ']' + ws.Name,
                np.float64(
                    data_array[col_idx]).tolist(),
                0,
                col_idx)  # start row, start col
        else:
            print('only 1 and 2 dimensional arrays supported')
    # origin.PutWorksheet('['+wb.Name+']'+ws.Name,
    # np.float64(data_array).T.tolist(), 0, col_idx) # start row, start col
    if user_defined is not None:
        # User Param Rows
        for idx, param in enumerate(user_defined):
            ws.Execute('wks.UserParam' + str(idx + 1) +
                       '=1; wks.UserParam' + str(idx + 1) + '$="' + param[0] + '";')
            ws.Execute('col(1)[' + param[0] + ']$="' + param[1] + '";')
        origin.Execute('wks.col1.width=10;')
    return origin, wb, ws


def createGraph_multiwks(origin, graph_name, template, templatePath, worksheets, x_cols, y_cols,
                         LineOrSym=None, auto_rescale=True,
                         x_scale=None, y_scale=None, x_label=None, y_label=None,
                         figsize=None):
    '''
    worksheets must be a list of worksheets
        Each worksheet must have same order of columns
    template is the full path and template filename
    x_cols, y_cols, and LineOrSym should be lists of same length
        each element of list is a different variable/column to plot
        x_col can be a single element list or an integer, and then the same value of x_col
        will be applied to every y_col
    auto_rescale is a bool. If true, axes scales will automatically re-scales
    x_scale, y_scale can be None (use origin default), "linear" or "log"
    x_label, y_label can be None (use template default) or string
    '''
    origin_version = get_origin_version(origin)
    # Create graph page and object
    templateFullPath = os.path.join(templatePath, template)
    # Create graph if doesn't already exist
    graph_layer = origin.FindGraphLayer(graph_name)
    if graph_layer is None:
        graph_name = origin.CreatePage(3, graph_name, templateFullPath)
        # Find the graph layer
        graph_layer = origin.FindGraphLayer(graph_name)
    # Check length of x_cols and y_cols
    if isinstance(x_cols, list) and isinstance(y_cols, list):
        if not len(x_cols) == len(y_cols):
            print(
                'length of x_cols != length of y_cols. Assuming same x_col for all y_cols')
            x_cols = [x_cols[0]] * len(y_cols)
    # if integer provided for x_cols but list for y_cols, assume same x_cols
    # for all y_cols
    elif isinstance(x_cols, int) and isinstance(y_cols, list):
        x_cols = [x_cols] * len(y_cols)
    elif isinstance(x_cols, int) and isinstance(y_cols, int):
        x_cols, y_cols = [x_cols], [y_cols]  # convert to lists
    # If LineOrSym not provided, assume line
    if LineOrSym is None:
        LineOrSym = ['Line'] * len(y_cols)
    elif isinstance(LineOrSym, str):
        LineOrSym = [LineOrSym] * len(y_cols)
    # Get dataplot collection from the graph layer
    dataPlots = graph_layer.DataPlots

    # Add data column by column to the graph
    # loop over worksheets within column loops so that data from same column
    # can be grouped. E.g. all PL data is in same column and will be grouped.
    for ci, x_col in enumerate(x_cols):
        for wi, worksheet in enumerate(worksheets):
            # Create a data range
            # Tested only on origin 2016 and 2018
            if origin_version < 9.5:  # 2016 or earlier
                dr = origin.NewDataRange  # Make a new datarange
            elif origin_version >= 9.50:  # 2018 or later
                dr = origin.NewDataRange()

            # Add data to data range
            # worksheet, start row, start col, end row (-1=last), end col
            dr.Add('X', worksheet, 0, x_col, -1, x_col)
            dr.Add('Y', worksheet, 0, y_cols[ci], -1, y_cols[ci])
            # Add data plot to graph layer
            # list of types: https://www.originlab.com/doc/LabTalk/ref/Plot-Type-IDs
            # 200 -- line
            # 201 -- symbol
            # 202 -- symbol+line
            # If specified, plot symbol. By default, plot line
            # https://www.originlab.com/doc/python/PyOrigin/Classes/GraphLayer-AddPlot
            if LineOrSym[ci] in ['Sym', 'Symbol', 'Symbols']:
                graph_layer.AddPlot(dr, 201)
                # Method when using win32com to connect
                # dataPlots.Add(dr, 201)
            elif LineOrSym[ci] == 'Line+Sym':
                graph_layer.AddPlot(dr, 202)
                # dataPlots.Add(dr, 202)
            else:
                graph_layer.AddPlot(dr, 200)
                # dataPlots.Add(dr, 200)
        # Group each column (This allows colors to be automatically incremented
        # and a single legend entry to be created for all the data sets with
        # the same legend entry)
        BeginIndex = ci * len(worksheets) + 1
        EndIndex = BeginIndex + len(worksheets) - 1
        graph_layer.Execute(
            'layer -g ' +
            str(BeginIndex) +
            ' ' +
            str(EndIndex) +
            ';')

    graph_layer.Execute('legend -r')

    # Set axes scales
    set_axis_scale(graph_layer, axis='x', scale=x_scale)
    set_axis_scale(graph_layer, axis='y', scale=y_scale)

    # Set axes titles (xb for bottom axis, yl for left y-axis, etc.)
    if x_label is not None:
        graph_layer.Execute('label -xb ' + x_label + ';')
    if y_label is not None:
        graph_layer.Execute('label -yl ' + y_label + ';')

    # Rescales axes
    # Rescale type: 1 = manual, 2 = normal, 3 = auto, 4 = fixed from, and 5 = fixed to.
    # graph_layer.Execute('layer.axis.rescale=3')
    if auto_rescale:
        graph_layer.Execute('Rescale')
    if figsize is not None:
        graph_page.SetWidth(figsize[0])
        graph_page.SetHeight(figsize[1])
    return graph_name
    # To exit, call origin.Exit()

# Could try to format from standard matplotlib keyword arguments, such as:
# figsize, markersize
# def format_from_mpl_kwargs(graph_page,graph_layer,**kwargs):
    # # Set figure size in inches
    # if figsize in kwargs.keys():
    # graph_page.SetWidth(figsize[0])
    # graph_page.SetHeight(figsize[1])

# '''
# Miscellaneous methods and commands that could be useful:

# Setting and getting height and width of graph page:
# origin.GraphPages(i).Height = 4
# origin.GraphPages(i).Width = 6

# Get number of workbooks, pages, etc.
# origin.WorksheetPages.Count
# origin.GraphPages.Count
# etc.

# Get the parent workbook of a worksheet
# worksheets[0].Parent.Name
#     This also works to get the parent with graph layers
# (more docs here https://www.originlab.com/doc/COM/Classes/)
# '''
