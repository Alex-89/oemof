# -*- coding: utf-8 -*-
"""
Created on Tue Jul 28 12:04:21 2015

@author: uwe
"""
from matplotlib import pyplot as plt
import db
import numpy as np
import holiday
import logging
import pandas as pd
from math import ceil as round_up
from datetime import time as settime


class electric_building():
    ''

    def __init__(self, bdew=None, **kwargs):
        # slp is of type bdew_elec_slp!
        self.__elec_demand__ = (
            bdew.slp[kwargs['selp_type']] /
            bdew.slp[kwargs['selp_type']].sum(0) *
            kwargs['annual_elec_demand'])

    @property
    def load(self):
        return self.__elec_demand__


class heat_building():
    ''
    def __init__(self, year, time_df, **kwargs):
        self.__year__ = year
        self.__time_df__ = time_df
        self.__time_df__['weekday'].mask(
            self.__time_df__['weekday'] == 0, 7, True)
        self.__heat_demand__ = self.create_slp(**kwargs)
        self.__temp_int__ = self.temp_interval()

    def temp_geo_series(self):
        '''
        A new temperature vector is generated containing a multy-day
        average temperature as needed in the load profile function.

        Notes
        -----
        Equation for the mathematical series of the average tempaerature [1]_:

        .. math::
            T=\frac{T_{t}+0.5\cdot T_{t-1}+0.25\cdot T_{t-2}+
                    0.125\cdot T_{t-3}}{1+0.5+0.25+0.125}$
        with :math:`T_t` = Average temperature on the present day
             :math:`T_{t-1}` = Average temperature on the previous day ...

        References
        ----------
        .. [1] `BDEW <https://www.avacon.de/cps/rde/xbcr/avacon/Netze_Lieferanten_Netznutzung_Lastprofilverfahren_Leitfaden_SLP_Gas.pdf>`_, BDEW Documentation for heat profiles.
        '''
        self.__time_df__['temp'] = pd.read_csv(
            filepath_or_buffer='/home/uwe/test.csv')['temp']
        tem = self.__time_df__['temp'].resample('D', how='mean').reindex(
            self.__time_df__.index).fillna(method="ffill")
        return (tem + 0.5 * np.roll(tem, 24) + 0.25 * np.roll(tem, 48) +
                0.125 * np.roll(tem, 72)) / 1.875

    def temp_interval(self):
        '''
        Appoints the corresponding temperature interval to each temperature in
        the temperature vector.
        '''
        temp = self.temp_geo_series()
        temp_dict = ({
            -20: 1, -19: 1, -18: 1, -17: 1, -16: 1, -15: 1, -14: 2,
            -13: 2, -12: 2, -11: 2, -10: 2, -9: 3, -8: 3, -7: 3, -6: 3, -5: 3,
            -4: 4, -3: 4, -2: 4, -1: 4, 0: 4, 1: 5, 2: 5, 3: 5, 4: 5, 5: 5,
            6: 6, 7: 6, 8: 6, 9: 6, 10: 6, 11: 7, 12: 7, 13: 7, 14: 7, 15: 7,
            16: 8, 17: 8, 18: 8, 19: 8, 20: 8, 21: 9, 22: 9, 23: 9, 24: 9,
            25: 9, 26: 10, 27: 10, 28: 10, 29: 10, 30: 10, 31: 10, 32: 10,
            33: 10, 34: 10, 35: 10, 36: 10, 37: 10, 38: 10, 39: 10, 40: 10})
        temp_rounded = [round_up(i) for i in temp]
        temp_int = [temp_dict[i] for i in temp_rounded]
        return np.transpose(np.array(temp_int))

    def get_h_values(self, **kwargs):
        '''Determine the h-values'''
        # Create the condition to retrieve the hour_factors from the database
        condition = (
            "building_class = {building_class} and type = upper('{shlp_type}')"
            ).format(**kwargs)

        # Retrieve the hour factors and write them into a DataFrame
        hour_factors = pd.DataFrame.from_dict(rdb.fetch_columns(
            main_dt['basic'], 'demand', 'shlp_hour_factors', columns=[
                'hour_of_day', 'weekday']
            + ['temp_intervall_{0:02.0f}'.format(x) for x in range(1, 11)],
            as_np=True, orderby='id', where_string=condition))

        # Join the two DataFrames on the columns 'hour' and 'hour_of_the_day'
        # or ['hour' 'weekday'] and ['hour_of_the_day', 'weekday'] if it is
        # not a residential slp.
        residential = kwargs['building_class'] > 0

        left_cols = ['hour_of_day'] + (['weekday'] if not residential else [])
        right_cols = ['hour'] + (['weekday'] if not residential else [])

        SF_mat = pd.DataFrame.merge(
            hour_factors, time_df, left_on=left_cols, right_on=right_cols,
            how='outer', left_index=True).sort().drop(
            left_cols + right_cols, 1)

        # Determine the h values
        h = np.array(SF_mat)[np.array(range(0, 8760))[:], (
            self.__temp_int__ - 1)[:]]
        return np.array(list(map(float, h[:])))

    def get_sigmoid_parameter(self, **kwargs):
        ''' Retrieve the sigmoid parameters from the database'''

        condition = """building_class={building_class} and wind_impact=
        {wind_class} and type=upper('{shlp_type}')""".format(**kwargs)

        sigmoid = rdb.fetch_columns(
            main_dt['basic'], 'demand', 'shlp_sigmoid_parameters', columns=[
                'parameter_{0}'.format(x) for x in ['a', 'b', 'c', 'd']],
            as_np=True, where_string=condition)

        A = float(sigmoid['parameter_a'])
        B = float(sigmoid['parameter_b'])
        C = float(sigmoid['parameter_c'])
        D = float(sigmoid['parameter_d']) if kwargs.get(
            'ww_incl', True) else 0
        return A, B, C, D

    def get_weekday_parameter(self, **kwargs):
        ''' Retrieve the weekdayparameter from the database'''
        F_df = pd.DataFrame.from_dict(rdb.fetch_columns(
            main_dt['basic'], 'demand', 'shlp_wochentagsfaktoren',
            columns=['wochentagsfaktor'], as_np=True, where_column='typ',
            orderby='wochentag', where_condition=(
                kwargs['shlp_type'].upper())))
        F_df['weekdays'] = F_df.index + 1

        return np.array(list(map(float, pd.DataFrame.merge(
            F_df, time_df, left_on='weekdays', right_on='weekday', how='outer',
            left_index=True).sort()['wochentagsfaktor'])))

    def create_slp(self, **kwargs):
        '''Calculation of the hourly heat demand using the bdew-equations'''
        SF = self.get_h_values(**kwargs)
        [A, B, C, D] = self.get_sigmoid_parameter(**kwargs)
        F = self.get_weekday_parameter(**kwargs)

        h = (A / (1 + (B / (self.__time_df__['temp'] - 40)) ** C) + D)
        KW = (kwargs['annual_heat_demand'] /
              (sum(h * F) / 24))
        return (KW * h * F * SF)

    @property
    def load(self):
        return self.__heat_demand__


class bdew_elec_slp():
    'Generate electrical standardized load profiles based on the BDEW method.'

    def __init__(self, year, time_df, periods=None):
        if periods is None:
            self.__periods__ = {
                'summer1': [5, 15, 9, 14],  # summer: 15.05. to 14.09
                'transition1': [3, 21, 5, 14],  # transition1 :21.03. to 14.05
                'transition2': [9, 15, 10, 31],  # transition2 :15.09. to 31.10
                'winter1': [1, 1, 3, 20],  # winter1:  01.01. to 20.03
                'winter2': [11, 1, 12, 31],  # winter2: 01.11. to 31.12
                }
        else:
            self.__periods__ = periods

        self.__year__ = year
        self.__time_df__ = time_df
        self.__slp_frame__ = self.all_load_profiles()

    def all_load_profiles(self):
        slp_types = ['h0', 'g0', 'g1', 'g2', 'g3', 'g4', 'g5', 'g6', 'l0',
                     'l1', 'l2']
        new_df = self.create_bdew_load_profiles(slp_types)

        # Add the slp for the industrial group
        new_df['i0'] = self.simple_industrial_heat_profile(self.__time_df__)

        new_df.drop(['hour', 'weekday'], 1, inplace=True)
        # TODO: Gleichmäßig normalisieren der i0-Lastgang hat höhere
        # Jahressumme als die anderen.
        return new_df

    def create_bdew_load_profiles(self, slp_types):
        '''
        Calculates the hourly electricity load profile in MWh/h of a region.
        '''

        # Write values from the data base to a DataFrame
        # The dates are not real dates but helpers to calculate the mean values
        tmp_df = pd.read_sql_table(
            table_name='selp_series', con=db.db_engine(), schema='demand',
            columns=['period', 'weekday'] + slp_types)

        tmp_df.set_index(pd.date_range(pd.datetime(2007, 1, 1, 0),
                                       periods=2016, freq='15Min'),
                         inplace=True)

        # Create a new DataFrame to collect the results
        time_df = self.__time_df__

        # All holidays(0) are set to sunday(7)
        time_df.weekday = self.__time_df__.weekday.replace(0, 7)
        new_df = time_df.copy()

        # Create an empty column for all slp types and calculate the hourly
        # mean.
        how = {'period': 'last', 'weekday': 'last'}
        for slp_type in slp_types:
            new_df[slp_type] = 0
            how[slp_type] = 'mean'
        tmp_df = tmp_df.resample('H', how=how)

        # Inner join the slps on the time_df to the slp's for a whole year
        tmp_df['hour_of_day'] = tmp_df.index.hour + 1
        left_cols = ['hour_of_day', 'weekday']
        right_cols = ['hour', 'weekday']
        tmp_df = tmp_df.reset_index()
        tmp_df.pop('index')

        for p in self.__periods__.keys():
            a = pd.datetime(self.__year__, self.__periods__[p][0],
                            self.__periods__[p][1], 0, 0)
            b = pd.datetime(self.__year__, self.__periods__[p][2],
                            self.__periods__[p][3], 23, 59)
            new_df.update(pd.DataFrame.merge(
                tmp_df[tmp_df['period'] == p[:-1]], time_df[a:b],
                left_on=left_cols, right_on=right_cols,
                how='inner', left_index=True).sort().drop(['hour_of_day'], 1))

        return new_df

    def simple_industrial_heat_profile(self, df):
        ''

        # TODO: Remove the hard coded values
        am = settime(7, 0, 0)
        pm = settime(23, 30, 0)

        df['ind'] = 0

        # Day(am to pm), night (pm to am), week day (week),
        # weekend day (weekend)
        week = [1, 2, 3, 4, 5]
        weekend = [0, 6, 7]

        df['ind'].mask(df['weekday'].between_time(am, pm).isin(week), 0.8,
                       True)
        df['ind'].mask(df['weekday'].between_time(pm, am).isin(week), 0.6,
                       True)
        df['ind'].mask(df['weekday'].between_time(am, pm).isin(weekend), 0.9,
                       True)
        df['ind'].mask(df['weekday'].between_time(pm, am).isin(weekend), 0.7,
                       True)

        if df['ind'].isnull().any(axis=0):
            logging.error('NAN value found in industrial load profile')
        return df.pop('ind')

    @property
    def slp(self):
        return self.__slp_frame__


def create_basic_dataframe(year, place):
    '''This function is just for testing later on the dataframe is passed.'''

    # Create a temporary DataFrame to calculate the heat demand
    time_df = pd.DataFrame(
        index=pd.date_range(
            pd.datetime(year, 1, 1, 0), periods=8760, freq='H'),
        columns=['weekday', 'hour', 'date'])

    holidays = holiday.get_german_holidays(year, place)

    # Add a column 'hour of the day to the DataFrame
    time_df['hour'] = time_df.index.hour + 1
    time_df['weekday'] = time_df.index.weekday + 1
    time_df['date'] = time_df.index.date
    time_df['elec'] = 0
    time_df['heat'] = 0

    # Set weekday to Holiday (0) for all holidays
    time_df['weekday'].mask(pd.to_datetime(time_df['date']).isin(
        pd.to_datetime(list(holidays.keys()))), 0, True)
    return time_df


if __name__ == "__main__":
    year = 2007
    define_elec_buildings = [
        {'annual_elec_demand': 2000,
         'selp_type': 'h0'},
        {'annual_elec_demand': 2000,
         'selp_type': 'g0'},
        {'annual_elec_demand': 2000,
         'selp_type': 'i0'}]

    define_heat_buildings = [
        {'building_class': 11,
         'wind_class': 0,
         'annual_heat_demand': 5000,
         'shlp_type': 'efh'},
        {'building_class': 5,
         'wind_class': 1,
         'annual_heat_demand': 5000,
         'shlp_type': 'mfh'},
        {'selp_type': 'g0',
         'building_class': 0,
         'wind_class': 1,
         'annual_heat_demand': 3000,
         'shlp_type': 'ghd'}]

    time_df = create_basic_dataframe(year, ['Deutschland', 'ST'])

#    a = bdew_elec_slp(year, time_df)
#    elec_buildings = []
#    for building_def in define_elec_buildings:
#        elec_buildings.append(electric_building(bdew=a, **building_def))
#
#    for building in elec_buildings:
#        building.load.plot()
#    plt.show()

    heat_buildings = []
    for building_def in define_heat_buildings:
        heat_buildings.append(heat_building(year, time_df, **building_def))

    for building in heat_buildings:
        building.load.plot()
    plt.show()