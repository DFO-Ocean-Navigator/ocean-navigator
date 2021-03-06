# vim: set fileencoding=utf-8 :

from mpl_toolkits.axes_grid1 import make_axes_locatable
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import re
import colormap
import utils
from oceannavigator.util import get_dataset_url
import line
from flask_babel import gettext
from data import open_dataset


class HovmollerPlotter(line.LinePlotter):

    def __init__(self, dataset_name, query, format):
        self.plottype = "hovmoller"
        super(HovmollerPlotter, self).__init__(dataset_name, query, format)

    def load_data(self):
        with open_dataset(get_dataset_url(self.dataset_name)) as dataset:
            latvar, lonvar = utils.get_latlon_vars(dataset)

            if self.depth:
                if self.depth == 'bottom':
                    self.depth_value = 'Bottom'
                    self.depth_unit = ''
                else:
                    self.depth = np.clip(int(self.depth), 0,
                                         len(dataset.depths) - 1)
                    self.depth_value = np.round(dataset.depths[self.depth])
                    self.depth_unit = "m"
            else:
                self.depth_value = 0
                self.depth_unit = "m"

            self.fix_startend_times(dataset)

            time = range(self.starttime, self.endtime + 1)
            if len(self.variables) > 1:
                v = []
                for name in self.variables:
                    pts, distance, t, value = dataset.get_path(
                        self.points,
                        self.depth,
                        time,
                        name
                    )
                    v.append(value ** 2)

                value = np.sqrt(np.ma.sum(v, axis=0))
            else:
                pts, distance, t, value = dataset.get_path(
                    self.points,
                    self.depth,
                    time,
                    self.variables[0]
                )

            self.path_points = pts
            self.distance = distance

            variable_names = self.get_variable_names(dataset, self.variables)
            variable_units = self.get_variable_units(dataset, self.variables)
            scale_factors = self.get_variable_scale_factors(dataset,
                                                            self.variables)

            self.variable_unit, self.data = self.kelvin_to_celsius(
                variable_units[0],
                value
            )
            self.data = np.multiply(self.data, scale_factors[0])
            self.variable_name = variable_names[0]
            self.data = self.data.transpose()

            if self.cmap is None:
                self.cmap = colormap.find_colormap(self.variable_name)

            self.times = dataset.timestamps[self.starttime:self.endtime + 1]

    def plot(self):
        # Figure size
        figuresize = map(float, self.size.split("x"))
        fig = plt.figure(figsize=figuresize, dpi=self.dpi)

        if self.showmap:
            width = 2
            width_ratios = [2, 7]
        else:
            width = 1
            width_ratios = [1]

        gs = gridspec.GridSpec(1, width, width_ratios=width_ratios)

        if self.showmap:
            # Plot the path on a map
            plt.subplot(gs[0])

            utils.path_plot(self.path_points)

        if self.scale:
            vmin = self.scale[0]
            vmax = self.scale[1]
        else:
            vmin = np.amin(self.data)
            vmax = np.amax(self.data)
            if np.any(map(
                lambda x: re.search(x, self.variable_name, re.IGNORECASE),
                [
                    "velocity",
                    "surface height",
                    "wind"
                ]
            )):
                vmin = min(vmin, -vmax)
                vmax = max(vmax, -vmin)
            if len(self.variables) > 1:
                vmin = 0

        if self.showmap:
            plt.subplot(gs[1])

        if len(self.variables) > 1:
            self.variable_name = self.vector_name(self.variable_name)

        c = plt.pcolormesh(self.distance, self.times, self.data,
                           cmap=self.cmap,
                           shading='gouraud',
                           vmin=vmin,
                           vmax=vmax)
        ax = plt.gca()
        ax.yaxis_date()
        ax.yaxis.grid(True)
        ax.set_axis_bgcolor('dimgray')

        plt.xlabel(gettext("Distance (km)"))
        plt.xlim([self.distance[0], self.distance[-1]])

        divider = make_axes_locatable(plt.gca())
        cax = divider.append_axes("right", size="5%", pad=0.05)
        bar = plt.colorbar(c, cax=cax)
        bar.set_label("%s (%s)" % (self.variable_name,
                                   utils.mathtext(self.variable_unit)))

        if self.depth == 'bottom':
            depth_label = " at Bottom"
        else:
            depth_label = " at %d %s" % (self.depth_value, self.depth_unit)

        fig.suptitle(gettext(u"Hovm\xf6ller Diagram for %s%s,\n%s") % (
            self.variable_name,
            depth_label,
            self.name
        ))

        fig.tight_layout(pad=3, w_pad=4)
        fig.subplots_adjust(top=0.92)

        return super(HovmollerPlotter, self).plot(fig)
