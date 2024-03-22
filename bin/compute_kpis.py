# -*- coding: utf-8 -*-

from __future__ import division
from __future__ import print_function

# =========================== adjust path =====================================

import os
import sys

import netaddr

if __name__ == '__main__':
    here = sys.path[0]
    sys.path.insert(0, os.path.join(here, '..'))

# ========================== imports ==========================================

import json
import glob
import numpy as np
import json
import csv
import pandas as pd
import math

from SimEngine import SimLog
import SimEngine.Mote.MoteDefines as d

# =========================== defines =========================================

DAGROOT_ID = 0  # we assume first mote is DAGRoot
DAGROOT_IP = 'fd00::1:0'
BATTERY_AA_CAPACITY_mAh = 2821.5

# =========================== decorators ======================================

def openfile(func):
    def inner(inputfile):
        with open(inputfile, 'r') as f:
            return func(f)
    return inner

# =========================== helpers =========================================

def mean(numbers):
    return float(sum(numbers)) / max(len(numbers), 1)

def init_mote():
    return {
        'upstream_num_tx': 0,
        'upstream_num_rx': 0,
        'upstream_num_lost': 0,
        'join_asn': None,
        'join_time_s': None,
        'sync_asn': None,
        'rpl_asn' : None,
        'rpl_first_asn' : None,
        'rpl_parent_change_num' : None,
        'rpl_time_s' : None,
        'sync_time_s': None,
        'charge_asn': None,
        'charge_asn_before_sync': None,
        'upstream_pkts': {},
        'latencies': [],
        'hops': [],
        'charge': None,
        'charge_before_sync': None,
        'lifetime_AA_years': None,
        'avg_current_uA': None,
        'neighbor_num': 0,
        'rank' : d.RPL_INFINITE_RANK,
        'rpl_join' : False,
        'avg_hops' : None,
        'num_minimal_cells_rx' : {},
        'num_minimal_cells_tx' : {},
        'minimal_cell_utilization' : {},
        'neighbor_num_per_minimal_cell' : {},
        'neighbor_rssi_sum' : {}
    }

# =========================== KPIs ============================================

@openfile
def kpis_all(inputfile):

    allstats = {} # indexed by run_id, mote_id
    networkStats = {}

    file_settings = json.loads(inputfile.readline())  # first line contains settings

    # === gather raw stats

    for line in inputfile:
        logline = json.loads(line)

        # shorthands
        run_id = logline['_run_id']
        if '_asn' in logline: # TODO this should be enforced in each line
            asn = logline['_asn']
        if '_mote_id' in logline: # TODO this should be enforced in each line
            mote_id = logline['_mote_id']

        # populate
        if run_id not in allstats:
            allstats[run_id] = {}

        if run_id not in networkStats:
            networkStats[run_id] = {}

        if (
                ('_mote_id' in logline)
                and
                (mote_id not in allstats[run_id])
                # and
                # (mote_id != DAGROOT_ID)
            ):
            allstats[run_id][mote_id] = init_mote()

        if   logline['_type'] == SimLog.LOG_TSCH_SYNCED['type']:
            # sync'ed

            # shorthands
            mote_id    = logline['_mote_id']

            # only log non-dagRoot sync times
            if mote_id == DAGROOT_ID:
                continue
            
            # 동기화된 모트 목록을 저장해둠
            if 'sync_motes' not in networkStats[run_id]:
                networkStats[run_id]['sync_motes'] = {}
            
            networkStats[run_id]['sync_motes'][mote_id] = True

            allstats[run_id][mote_id]['sync_asn']  = asn
            allstats[run_id][mote_id]['sync_time_s'] = asn*file_settings['tsch_slotDuration']

        elif logline['_type'] == SimLog.LOG_TSCH_DESYNCED['type']:

            # shorthands
            mote_id    = logline['_mote_id']

            # only log non-dagRoot sync times
            if mote_id == DAGROOT_ID:
                continue

            # 비동기화된 모트들을 삭제함
            networkStats[run_id]['sync_motes'][mote_id] = False

        elif logline['_type'] == SimLog.LOG_SECJOIN_JOINED['type']:
            # joined

            # shorthands
            mote_id    = logline['_mote_id']

            # only log non-dagRoot join times
            if mote_id == DAGROOT_ID:
                continue

            # populate
            assert allstats[run_id][mote_id]['sync_asn'] is not None
            allstats[run_id][mote_id]['join_asn']  = asn
            allstats[run_id][mote_id]['join_time_s'] = asn*file_settings['tsch_slotDuration']

        elif logline['_type'] == SimLog.LOG_APP_TX['type']:
            # packet transmission

            # shorthands
            mote_id    = logline['_mote_id']
            dstIp      = logline['packet']['net']['dstIp']
            appcounter = logline['packet']['app']['appcounter']

            # only log upstream packets
            if dstIp != DAGROOT_IP:
                continue

            # populate
            assert allstats[run_id][mote_id]['join_asn'] is not None
            if appcounter not in allstats[run_id][mote_id]['upstream_pkts']:
                allstats[run_id][mote_id]['upstream_pkts'][appcounter] = {
                    'hops': 0,
                }

            allstats[run_id][mote_id]['upstream_pkts'][appcounter]['tx_asn'] = asn

        elif logline['_type'] == SimLog.LOG_APP_RX['type']:
            # packet reception

            # shorthands
            mote_id    = netaddr.IPAddress(logline['packet']['net']['srcIp']).words[-1]
            dstIp      = logline['packet']['net']['dstIp']
            hop_limit  = logline['packet']['net']['hop_limit']
            appcounter = logline['packet']['app']['appcounter']

            # only log upstream packets
            if dstIp != DAGROOT_IP:
                continue

            allstats[run_id][mote_id]['upstream_pkts'][appcounter]['hops']   = (
                d.IPV6_DEFAULT_HOP_LIMIT - hop_limit + 1
            )
            allstats[run_id][mote_id]['upstream_pkts'][appcounter]['rx_asn'] = asn

        elif logline['_type'] == SimLog.LOG_RADIO_STATS['type']:
            # shorthands
            mote_id    = logline['_mote_id']

            # only log non-dagRoot charge
            if mote_id == DAGROOT_ID:
                continue
            
            # 전체 에너지 소모량
            charge =  logline['idle_listen'] * d.CHARGE_IdleListen_uC
            charge += logline['tx_data_rx_ack'] * d.CHARGE_TxDataRxAck_uC
            charge += logline['rx_data_tx_ack'] * d.CHARGE_RxDataTxAck_uC
            charge += logline['tx_data'] * d.CHARGE_TxData_uC
            charge += logline['rx_data'] * d.CHARGE_RxData_uC
            charge += logline['sleep'] * d.CHARGE_Sleep_uC

            allstats[run_id][mote_id]['charge_asn'] = asn
            allstats[run_id][mote_id]['charge']     = charge

            # 싱크 전 에너지 소모량
            is_sync = False
            if 'sync_motes' in networkStats[run_id] and mote_id in networkStats[run_id]['sync_motes'] and networkStats[run_id]['sync_motes'][mote_id]:
                is_sync = True

            if not is_sync:
                charge_before_sync =  logline['idle_listen'] * d.CHARGE_IdleListen_uC
                charge_before_sync += logline['tx_data_rx_ack'] * d.CHARGE_TxDataRxAck_uC
                charge_before_sync += logline['rx_data_tx_ack'] * d.CHARGE_RxDataTxAck_uC
                charge_before_sync += logline['tx_data'] * d.CHARGE_TxData_uC
                charge_before_sync += logline['rx_data'] * d.CHARGE_RxData_uC
                charge_before_sync += logline['sleep'] * d.CHARGE_Sleep_uC

                allstats[run_id][mote_id]['charge_asn_before_syn'] = asn
                allstats[run_id][mote_id]['charge_before_sync']    = charge

        elif logline['_type'] == SimLog.LOG_USER_MINIMALCELL_TX['type']:
            if 'minimalcell_tx' not in networkStats[run_id]:
                networkStats[run_id]['minimalcell_tx'] = {}

            # 미니멀셀 사용 횟수를 저장한다.
            if 'num_cell_used' not in networkStats[run_id]['minimalcell_tx']:
                networkStats[run_id]['minimalcell_tx']['num_cell_used'] = 1
            else:
                networkStats[run_id]['minimalcell_tx']['num_cell_used'] += 1
    
            # 충돌 여부를 저장할 변수
            collision_detected = False

            # 패킷의 종류가 2개 이상일 경우 충돌이 발생함
            if len(logline['num_per_packet_type']) > 1:
                collision_detected = True                

            # 미니멀셀에서 데이터를 전송한 패킷의 종류와 개수를 저장한다.
            for key, value in logline['num_per_packet_type'].items():
                if 'num_per_packet_type' not in networkStats[run_id]['minimalcell_tx']:
                    networkStats[run_id]['minimalcell_tx']['num_per_packet_type'] = {}

                if 'num_per_packet_type_in_if' not in networkStats[run_id]['minimalcell_tx']:
                    networkStats[run_id]['minimalcell_tx']['num_per_packet_type_in_if'] = {}

                if 'num_per_packet_type_in_no_if' not in networkStats[run_id]['minimalcell_tx']:
                    networkStats[run_id]['minimalcell_tx']['num_per_packet_type_in_no_if'] = {}

                # 동시에 전송한 패킷이 2개 이상일 경우 충돌이 발생함
                if value > 1 :
                    collision_detected = True

                # 미니멀 셀에서 전송된 패킷의 수를 타입별로 저장함
                if key not in networkStats[run_id]['minimalcell_tx']['num_per_packet_type']:
                    networkStats[run_id]['minimalcell_tx']['num_per_packet_type'][key] = value
                else:
                    networkStats[run_id]['minimalcell_tx']['num_per_packet_type'][key] += value

                # 간섭이 발생한 환경에서 전송된 패킷 개수를 타입별로 저장함
                if collision_detected:
                    if key not in networkStats[run_id]['minimalcell_tx']['num_per_packet_type_in_if']:
                        networkStats[run_id]['minimalcell_tx']['num_per_packet_type_in_if'][key] = value
                    else:
                        networkStats[run_id]['minimalcell_tx']['num_per_packet_type_in_if'][key] += value
                else:
                    if key not in networkStats[run_id]['minimalcell_tx']['num_per_packet_type_in_no_if']:
                        networkStats[run_id]['minimalcell_tx']['num_per_packet_type_in_no_if'][key] = value
                    else:
                        networkStats[run_id]['minimalcell_tx']['num_per_packet_type_in_no_if'][key] += value

            # 미니멀 셀에서 간섭이 발생한 채널의 개수를 저장함
            if collision_detected:
                if 'num_collision_cell' not in networkStats[run_id]['minimalcell_tx']:
                    networkStats[run_id]['minimalcell_tx']['num_collision_cell'] = 1
                else:
                    networkStats[run_id]['minimalcell_tx']['num_collision_cell'] += 1
    
        # RPL 선호 부모 선택 여부 및 RPL 네트워크 참여 시간을 저장함
        elif logline['_type'] == SimLog.LOG_RPL_CHURN['type']:

            mote_id = logline['_mote_id']
            preferredParent = logline['preferredParent']

            if mote_id == DAGROOT_ID:
                continue
            
            # 변경할 부모의 주소가 있다면, RPL 네트워크에 참여했으며 참여한 시간을 저장한다.
            if preferredParent is None:
                allstats[run_id][mote_id]['rpl_join'] = False
                allstats[run_id][mote_id]['rpl_asn']  = None
                allstats[run_id][mote_id]['rpl_first_asn'] = None
            else :
                # 첫번째 부모 선택 시간을 따로 저장한다.
                if allstats[run_id][mote_id]['rpl_asn'] is None:
                    allstats[run_id][mote_id]['rpl_first_asn'] = asn

                if allstats[run_id][mote_id]['rpl_parent_change_num'] is None:
                    allstats[run_id][mote_id]['rpl_parent_change_num'] = 1
                else:
                    allstats[run_id][mote_id]['rpl_parent_change_num'] += 1

                allstats[run_id][mote_id]['rpl_join'] = True
                allstats[run_id][mote_id]['rpl_asn']  = asn
                allstats[run_id][mote_id]['rpl_time_s'] = asn*file_settings['tsch_slotDuration']

        # 미니멀 셀에서 전송된 패킷의 수신 결과를 저장함
        elif logline['_type'] == SimLog.LOG_USER_MINIMALCELL_RX['type']:

            if 'minimalcell_rx' not in networkStats[run_id]:
                networkStats[run_id]['minimalcell_rx'] = {}
            if 'num_per_packet_type' not in networkStats[run_id]['minimalcell_rx']:
                networkStats[run_id]['minimalcell_rx']['num_per_packet_type'] = {}
            if 'num_per_packet_type_in_if' not in networkStats[run_id]['minimalcell_rx']:
                networkStats[run_id]['minimalcell_rx']['num_per_packet_type_in_if'] = {}
            if 'num_per_packet_type_in_no_if' not in networkStats[run_id]['minimalcell_rx']:
                networkStats[run_id]['minimalcell_rx']['num_per_packet_type_in_no_if'] = {}
            rx_status = logline['rx_status']
            
            for txResult in rx_status:

                is_interference = txResult['is_interference']
                is_recv_success = txResult['is_recv_success']
                packet_type = txResult['num_per_packet_type']

                if 'fail' not in networkStats[run_id]['minimalcell_rx']:
                    networkStats[run_id]['minimalcell_rx']['fail'] = 0
                if 'success' not in networkStats[run_id]['minimalcell_rx']:
                    networkStats[run_id]['minimalcell_rx']['success'] = 0
                if 'if' not in networkStats[run_id]['minimalcell_rx']:
                    networkStats[run_id]['minimalcell_rx']['if'] = 0
                if 'no_if' not in networkStats[run_id]['minimalcell_rx']:
                    networkStats[run_id]['minimalcell_rx']['no_if'] = 0

                if 'no_if_fail' not in networkStats[run_id]['minimalcell_rx']:
                    networkStats[run_id]['minimalcell_rx']['no_if_fail'] = 0
                if 'if_fail' not in networkStats[run_id]['minimalcell_rx']:
                    networkStats[run_id]['minimalcell_rx']['if_fail'] = 0
                if 'no_if_success' not in networkStats[run_id]['minimalcell_rx']:
                    networkStats[run_id]['minimalcell_rx']['no_if_success'] = 0
                if 'if_success' not in networkStats[run_id]['minimalcell_rx']:
                    networkStats[run_id]['minimalcell_rx']['if_success'] = 0

                # 간섭 발생 여부와 무관하게 수신했는지 정리함
                if is_recv_success == False:
                    networkStats[run_id]['minimalcell_rx']['fail'] += 1
                else:
                    networkStats[run_id]['minimalcell_rx']['success'] += 1

                # 성공 여부와 무관하게 간섭됐는지만 정리함
                if is_interference == False:
                    networkStats[run_id]['minimalcell_rx']['if'] += 1
                else:
                    networkStats[run_id]['minimalcell_rx']['no_if'] += 1

                # 간섭 발생 여부와 패킷을 정상적으로 수신했는지 정리함
                if is_interference == False and is_recv_success == False:
                    networkStats[run_id]['minimalcell_rx']['no_if_fail'] += 1
                elif is_interference == True and is_recv_success == False:
                    networkStats[run_id]['minimalcell_rx']['if_fail'] += 1
                elif is_interference == False and is_recv_success == True:
                    networkStats[run_id]['minimalcell_rx']['no_if_success'] += 1
                else:
                    networkStats[run_id]['minimalcell_rx']['if_success'] += 1

                # 수신된 패킷을 종류별로 저장한다.
                if is_recv_success:
                    if packet_type not in networkStats[run_id]['minimalcell_rx']['num_per_packet_type']:
                        networkStats[run_id]['minimalcell_rx']['num_per_packet_type'][packet_type] = 1
                    else:
                        networkStats[run_id]['minimalcell_rx']['num_per_packet_type'][packet_type] += 1
    
                    if is_interference:
                        if packet_type not in networkStats[run_id]['minimalcell_rx']['num_per_packet_type_in_if']:
                            networkStats[run_id]['minimalcell_rx']['num_per_packet_type_in_if'][packet_type] = 1
                        else:
                            networkStats[run_id]['minimalcell_rx']['num_per_packet_type_in_if'][packet_type] += 1
                    else:
                        if packet_type not in networkStats[run_id]['minimalcell_rx']['num_per_packet_type_in_no_if']:
                            networkStats[run_id]['minimalcell_rx']['num_per_packet_type_in_no_if'][packet_type] = 1
                        else:
                            networkStats[run_id]['minimalcell_rx']['num_per_packet_type_in_no_if'][packet_type] += 1

        # 장치별 이웃 수를 저장함
        elif logline['_type'] == SimLog.LOG_USER_NEIGHBOR_NUM['type']:

            mote_id = logline['_mote_id']
            neighbor_num = logline['neighbor_num']

            allstats[run_id][mote_id]['neighbor_num'] = neighbor_num
        
        # 장치별 RPL Rank 값을 저장함
        elif logline['_type'] == SimLog.LOG_USER_RPL_RANK['type']:
            
            mote_id = logline['_mote_id']
            rank = logline['rank']

            if mote_id == DAGROOT_ID or rank is None:
                continue

            allstats[run_id][mote_id]['rank'] = rank
        elif logline['_type'] == SimLog.LOG_USER_MINIMAL_CELL_CONGESTION['type']:
            mote_id = logline['_mote_id']
            num_minimal_cells_rx =  logline['num_minimal_cells_rx']
            num_minimal_cells_tx =  logline['num_minimal_cells_tx']
            minimal_cell_utilization = logline['minimal_cell_utilization']
            neighbor_num = logline['neighbor_num']
            neighbor_rssi_sum = logline['neighbor_rssi_sum']

            if minimal_cell_utilization is None:
                continue

            allstats[run_id][mote_id]['num_minimal_cells_rx'][asn] = num_minimal_cells_rx
            allstats[run_id][mote_id]['num_minimal_cells_tx'][asn] = num_minimal_cells_tx
            allstats[run_id][mote_id]['minimal_cell_utilization'][asn] = minimal_cell_utilization
            allstats[run_id][mote_id]['neighbor_num_per_minimal_cell'][asn] = neighbor_num
            allstats[run_id][mote_id]['neighbor_rssi_sum'][asn] = neighbor_rssi_sum

    # === compute advanced motestats

    for (run_id, per_mote_stats) in list(allstats.items()):
        for (mote_id, motestats) in list(per_mote_stats.items()):
            if mote_id != 0:

                if (motestats['sync_asn'] is not None) and (motestats['charge_asn'] is not None):
                    # avg_current, lifetime_AA
                    if (
                            (motestats['charge'] <= 0)
                            or
                            (motestats['charge_asn'] <= motestats['sync_asn'])
                        ):
                        motestats['lifetime_AA_years'] = 'N/A'
                    else:
                        motestats['avg_current_uA'] = motestats['charge']/float((motestats['charge_asn']-motestats['sync_asn']) * file_settings['tsch_slotDuration'])
                        assert motestats['avg_current_uA'] > 0
                        motestats['lifetime_AA_years'] = (BATTERY_AA_CAPACITY_mAh*1000/float(motestats['avg_current_uA']))/(24.0*365)
                if motestats['join_asn'] is not None:
                    # latencies, upstream_num_tx, upstream_num_rx, upstream_num_lost
                    for (appcounter, pktstats) in list(allstats[run_id][mote_id]['upstream_pkts'].items()):
                        motestats['upstream_num_tx']      += 1
                        if 'rx_asn' in pktstats:
                            motestats['upstream_num_rx']  += 1
                            thislatency = (pktstats['rx_asn']-pktstats['tx_asn'])*file_settings['tsch_slotDuration']
                            motestats['latencies']  += [thislatency]
                            motestats['hops']       += [pktstats['hops']]
                        else:
                            motestats['upstream_num_lost'] += 1
                    if (motestats['upstream_num_rx'] > 0) and (motestats['upstream_num_tx'] > 0):
                        motestats['latency_min_s'] = min(motestats['latencies'])
                        motestats['latency_avg_s'] = sum(motestats['latencies'])/float(len(motestats['latencies']))
                        motestats['latency_max_s'] = max(motestats['latencies'])
                        motestats['upstream_reliability'] = motestats['upstream_num_rx']/float(motestats['upstream_num_tx'])
                        motestats['avg_hops'] = sum(motestats['hops'])/float(len(motestats['hops']))

    # === network stats
    for (run_id, per_mote_stats) in list(allstats.items()):

        #-- define stats

        app_packets_sent = 0
        app_packets_received = 0
        app_packets_lost = 0
        joining_times = []
        rpl_times = []
        rpl_first_times = []
        sync_times = []
        us_latencies = []
        charge_consumed = []
        charge_consumed_before_sync = []
        lifetimes = []
        avg_hops = []
        slot_duration = file_settings['tsch_slotDuration']
        minimal_cell_utilization = []

        #-- compute stats

        for (mote_id, motestats) in list(per_mote_stats.items()):
            if mote_id == DAGROOT_ID:
                continue

            # counters

            app_packets_sent += motestats['upstream_num_tx']
            app_packets_received += motestats['upstream_num_rx']
            app_packets_lost += motestats['upstream_num_lost']

            # joining times

            if motestats['join_asn'] is not None:
                joining_times.append(motestats['join_asn'])

            if motestats['sync_asn'] is not None:
                sync_times.append(motestats['sync_asn'])

            if motestats['rpl_asn'] is not None:
                rpl_times.append(motestats['rpl_asn'])

            if motestats['rpl_first_asn'] is not None:
                rpl_first_times.append(motestats['rpl_first_asn'])
            # latency

            us_latencies += motestats['latencies']

            # current consumed

            charge_consumed.append(motestats['charge'])
            if motestats['lifetime_AA_years'] is not None:
                lifetimes.append(motestats['lifetime_AA_years'])
            charge_consumed = [
                value for value in charge_consumed if value is not None
            ]

            charge_consumed_before_sync.append(motestats['charge_before_sync'])
            charge_consumed_before_sync = [
                value for value in charge_consumed_before_sync if value is not None
            ]

            if motestats['avg_hops'] is not None:
                avg_hops.append(motestats['avg_hops'])

            # minimal cell utilization
            minimal_cell_utilization.append(mean(motestats['minimal_cell_utilization'].values()))
        #-- save stats

        allstats[run_id]['global-stats'] = {
            'e2e-upstream-delivery': [
                {
                    'name': 'E2E Upstream Delivery Ratio',
                    'unit': '%',
                    'value': (
                        1 - app_packets_lost / app_packets_sent
                        if app_packets_sent > 0 else 'N/A'
                    )
                },
                {
                    'name': 'E2E Upstream Loss Rate',
                    'unit': '%',
                    'value': (
                        app_packets_lost / app_packets_sent
                        if app_packets_sent > 0 else 'N/A'
                    )
                }
            ],
            'e2e-upstream-latency': [
                {
                    'name': 'E2E Upstream Latency',
                    'unit': 's',
                    'mean': (
                        mean(us_latencies)
                        if us_latencies else 'N/A'
                    ),
                    'min': (
                        min(us_latencies)
                        if us_latencies else 'N/A'
                    ),
                    'max': (
                        max(us_latencies)
                        if us_latencies else 'N/A'
                    ),
                    '99%': (
                        np.percentile(us_latencies, 99)
                        if us_latencies else 'N/A'
                    )
                },
                {
                    'name': 'E2E Upstream Latency',
                    'unit': 'slots',
                    'mean': (
                        mean(us_latencies) / slot_duration
                        if us_latencies else 'N/A'
                    ),
                    'min': (
                        min(us_latencies) / slot_duration
                        if us_latencies else 'N/A'
                    ),
                    'max': (
                        max(us_latencies) / slot_duration
                        if us_latencies else 'N/A'
                    ),
                    '99%': (
                        np.percentile(us_latencies, 99) / slot_duration
                        if us_latencies else 'N/A'
                    )
                }
            ],
            'charge-consumed': [
                {
                    'name': 'Charge Consumed',
                    'unit': 'mC',
                    'mean': (
                        mean(charge_consumed)
                        if charge_consumed else 'N/A'
                    ),
                    '99%': (
                        np.percentile(charge_consumed, 99)
                        if charge_consumed else 'N/A'
                    )
                }
            ],
            'charge-consumed-before-sync': [
                {
                    'name': 'Charge Consumed',
                    'unit': 'mA',
                    'mean': (
                        mean(charge_consumed_before_sync)
                        if charge_consumed_before_sync else 'N/A'
                    ),
                    '99%': (
                        np.percentile(charge_consumed_before_sync, 99)
                        if charge_consumed_before_sync else 'N/A'
                    )
                }
            ],
            'network_lifetime':[
                {
                    'name': 'Network Lifetime',
                    'unit': 'years',
                    'min': (
                        min(lifetimes)
                        if lifetimes else 'N/A'
                    ),
                    'total_capacity_mAh': BATTERY_AA_CAPACITY_mAh,
                }
            ],
            'joining-time': [
                {
                    'name': 'Joining Time',
                    'unit': 'slots',
                    'min': (
                        min(joining_times)
                        if joining_times else 'N/A'
                    ),
                    'max': (
                        max(joining_times)
                        if joining_times else 'N/A'
                    ),
                    'mean': (
                        mean(joining_times)
                        if joining_times else 'N/A'
                    ),
                    '99%': (
                        np.percentile(joining_times, 99)
                        if joining_times else 'N/A'
                    )
                }
            ],
            'rpl-time': [
                {
                    'name': 'Rpl Time',
                    'unit': 'slots',
                    'min': (
                        min(rpl_times)
                        if rpl_times else 'N/A'
                    ),
                    'max': (
                        max(rpl_times)
                        if rpl_times else 'N/A'
                    ),
                    'mean': (
                        mean(rpl_times)
                        if rpl_times else 'N/A'
                    ),
                    '99%': (
                        np.percentile(rpl_times, 99)
                        if rpl_times else 'N/A'
                    )
                }
            ],
            'rpl-first-time': [
                {
                    'name': 'Rpl Time',
                    'unit': 'slots',
                    'min': (
                        min(rpl_first_times)
                        if rpl_first_times else 'N/A'
                    ),
                    'max': (
                        max(rpl_first_times)
                        if rpl_first_times else 'N/A'
                    ),
                    'mean': (
                        mean(rpl_first_times)
                        if rpl_first_times else 'N/A'
                    ),
                    '99%': (
                        np.percentile(rpl_first_times, 99)
                        if rpl_first_times else 'N/A'
                    )
                }
            ],
            'sync-time': [
                {
                    'name': 'Sync Time',
                    'unit': 'slots',
                    'min': (
                        min(sync_times)
                        if sync_times else 'N/A'
                    ),
                    'max': (
                        max(sync_times)
                        if sync_times else 'N/A'
                    ),
                    'mean': (
                        mean(sync_times)
                        if sync_times else 'N/A'
                    ),
                    '99%': (
                        np.percentile(sync_times, 99)
                        if sync_times else 'N/A'
                    )
                }
            ],
            'app-packets-sent': [
                {
                    'name': 'Number of application packets sent',
                    'total': app_packets_sent
                }
            ],
            'app_packets_received': [
                {
                    'name': 'Number of application packets received',
                    'total': app_packets_received
                }
            ],
            'app_packets_lost': [
                {
                    'name': 'Number of application packets lost',
                    'total': app_packets_lost
                }
            ],
            'avg-hops': [
                {
                    'name': 'Average number of hops per mote',
                    'mean': mean(avg_hops)
                }
            ],
            'minimal-cell-utilization': [
                {
                    'name': 'Average utilization of minimal cell per mote',
                    'mean': mean(minimal_cell_utilization)
                }
            ]
        }

        # 실험을 위해 저장한 정보를 allstats에 이관함
        allstats[run_id]['global-stats']['minimalcell_tx'] = networkStats[run_id]['minimalcell_tx']
        allstats[run_id]['global-stats']['sync_motes'] = networkStats[run_id]['sync_motes']
        allstats[run_id]['global-stats']['minimalcell_rx'] = networkStats[run_id]['minimalcell_rx']

    #---------------------평균 계산---------------------
    avgStates = {}
 #=========================================================================================================================

    # num_cell_used 평균 계산
    avgStates['minimalcell_tx'] = {}
    avgStates['minimalcell_tx']['num_cell_used'] = {}
    num_cell_used_data = [stats['global-stats']['minimalcell_tx']['num_cell_used'] for run_id, stats in allstats.items()]
    avgStates['minimalcell_tx']['num_cell_used'] = calculate_stats(num_cell_used_data)
 
 #=========================================================================================================================

    # 전송 패킷에 따른 평균 계산
    avgStates['minimalcell_tx']['num_per_packet_type'] = {}
    packet_type_set = set()
    for run_id, stats in allstats.items():
        packet_type_set.update(stats['global-stats']['minimalcell_tx']['num_per_packet_type'].keys())

    for packet_type in packet_type_set:
        data = []
        for run_id, stats in allstats.items():
            if packet_type in stats['global-stats']['minimalcell_tx']['num_per_packet_type']:
                data.append(stats['global-stats']['minimalcell_tx']['num_per_packet_type'][packet_type])
            else:
                data.append(0)
        avgStates['minimalcell_tx']['num_per_packet_type'][packet_type] = calculate_stats(data)

    avgStates['minimalcell_tx']['num_per_packet_type_in_if'] = {}
    packet_type_set = set()
    for run_id, stats in allstats.items():
        packet_type_set.update(stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if'].keys())
 
    for packet_type in packet_type_set:
        data = []
        for run_id, stats in allstats.items():
            if packet_type in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if']:
                data.append(stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if'][packet_type])
            else:
                data.append(0)
        avgStates['minimalcell_tx']['num_per_packet_type_in_if'][packet_type] = calculate_stats(data)

    avgStates['minimalcell_tx']['num_per_packet_type_in_no_if'] = {}
    packet_type_set = set()
    for run_id, stats in allstats.items():
        packet_type_set.update(stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if'].keys())
 
    for packet_type in packet_type_set:
        data = []
        for run_id, stats in allstats.items():
            if packet_type in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']:
                data.append(stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if'][packet_type])
            else:
                data.append(0)
        avgStates['minimalcell_tx']['num_per_packet_type_in_no_if'][packet_type] = calculate_stats(data)

 #=========================================================================================================================

    # num_collision_cell 평균 계산
    avgStates['minimalcell_tx']['num_collision_cell'] = {}
    num_collision_cell_data = [stats['global-stats']['minimalcell_tx']['num_collision_cell'] for run_id, stats in allstats.items()]
    avgStates['minimalcell_tx']['num_collision_cell'] = calculate_stats(num_collision_cell_data)

 #=========================================================================================================================

    # 수신 및 간섭률에 대한 평균 계산
    avgStates['minimalcell_rx'] = {}
    avgStates['minimalcell_rx']['fail'] = {}
    fail_data = [stats['global-stats']['minimalcell_rx']['fail'] for run_id, stats in allstats.items()]
    avgStates['minimalcell_rx']['fail'] = calculate_stats(fail_data)

    avgStates['minimalcell_rx']['success'] = {}
    success_data = [stats['global-stats']['minimalcell_rx']['success'] for run_id, stats in allstats.items()]
    avgStates['minimalcell_rx']['success'] = calculate_stats(success_data)
    
    avgStates['minimalcell_rx']['if'] = {}
    if_data = [stats['global-stats']['minimalcell_rx']['if'] for run_id, stats in allstats.items()]
    avgStates['minimalcell_rx']['if'] = calculate_stats(if_data)

    avgStates['minimalcell_rx']['no_if'] = {}
    no_if_data = [stats['global-stats']['minimalcell_rx']['no_if'] for run_id, stats in allstats.items()]
    avgStates['minimalcell_rx']['no_if'] = calculate_stats(no_if_data)

    avgStates['minimalcell_rx']['no_if_fail'] = {}
    no_if_fail_data = [stats['global-stats']['minimalcell_rx']['no_if_fail'] for run_id, stats in allstats.items()]
    avgStates['minimalcell_rx']['no_if_fail'] = calculate_stats(no_if_fail_data)

    avgStates['minimalcell_rx']['if_fail'] = {}
    if_fail_data = [stats['global-stats']['minimalcell_rx']['if_fail'] for run_id, stats in allstats.items()]
    avgStates['minimalcell_rx']['if_fail'] = calculate_stats(if_fail_data)

    avgStates['minimalcell_rx']['no_if_success'] = {}
    no_if_success_data = [stats['global-stats']['minimalcell_rx']['no_if_success'] for run_id, stats in allstats.items()]
    avgStates['minimalcell_rx']['no_if_success'] = calculate_stats(no_if_success_data)

    avgStates['minimalcell_rx']['if_success'] = {}
    if_success_data = [stats['global-stats']['minimalcell_rx']['if_success'] for run_id, stats in allstats.items()]
    avgStates['minimalcell_rx']['if_success'] = calculate_stats(if_success_data)

 #=========================================================================================================================

    # 수신 패킷 전체에 패킷별로 평균 계산
    avgStates['minimalcell_rx']['num_per_packet_type'] = {}
    avgStates['minimalcell_rx']['rx_rate_per_packet_type'] = {}
    rcv_packet_type_set = set()
    for run_id, stats in allstats.items():
        rcv_packet_type_set.update(stats['global-stats']['minimalcell_rx']['num_per_packet_type'].keys())

    for packet_type in rcv_packet_type_set:
        data = []
        data_rate = []
        for run_id, stats in allstats.items():
            if packet_type in stats['global-stats']['minimalcell_rx']['num_per_packet_type'] and packet_type in stats['global-stats']['minimalcell_tx']['num_per_packet_type']:
                data.append(stats['global-stats']['minimalcell_rx']['num_per_packet_type'][packet_type])
                data_rate.append(stats['global-stats']['minimalcell_rx']['num_per_packet_type'][packet_type]/stats['global-stats']['minimalcell_tx']['num_per_packet_type'][packet_type])
            else:
                data.append(0)
                data_rate.append(0)

        avgStates['minimalcell_rx']['num_per_packet_type'][packet_type] = calculate_stats(data)
        avgStates['minimalcell_rx']['rx_rate_per_packet_type'][packet_type] = calculate_stats(data_rate)

    # RPl 타입 패킷에 대해 따로 계산
    rpl_data = []
    rpl_data_rate = []

    for run_id, stats in allstats.items():
        rpl = 0
        rpl_tx = 0
        if 'DIO' in stats['global-stats']['minimalcell_rx']['num_per_packet_type'] and 'DIO' in stats['global-stats']['minimalcell_tx']['num_per_packet_type']:
            rpl += stats['global-stats']['minimalcell_rx']['num_per_packet_type']['DIO']
            rpl_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type']['DIO']

        if 'DIS' in stats['global-stats']['minimalcell_rx']['num_per_packet_type'] and 'DIS' in stats['global-stats']['minimalcell_tx']['num_per_packet_type']:
            rpl += stats['global-stats']['minimalcell_rx']['num_per_packet_type']['DIS']
            rpl_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type']['DIS']

        if rpl_tx != 0:
            rpl_data.append(rpl)        
            rpl_data_rate.append(rpl/rpl_tx)
        else:
            rpl_data.append(0)        
            rpl_data_rate.append(0) 

    avgStates['minimalcell_rx']['num_per_packet_type']['rpl'] = calculate_stats(rpl_data)
    avgStates['minimalcell_rx']['rx_rate_per_packet_type']['rpl'] = calculate_stats(rpl_data_rate)
    
 #=========================================================================================================================

    # 간섭 환경에서 수신 패킷 전체에 패킷별로 평균 계산
    avgStates['minimalcell_rx']['num_per_packet_type_in_if'] = {}
    avgStates['minimalcell_rx']['rx_rate_per_packet_type_in_if'] = {}

    rcv_packet_type_set = set()
    for run_id, stats in allstats.items():
        rcv_packet_type_set.update(stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if'].keys())

    for packet_type in rcv_packet_type_set:
        data = []
        data_rate = []
        for run_id, stats in allstats.items():
            if packet_type in stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if'] and packet_type in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if']:
                data.append(stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if'][packet_type])
                data_rate.append((stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if'][packet_type])/stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if'][packet_type])
            else:
                data.append(0)
                data_rate.append(0)

        avgStates['minimalcell_rx']['num_per_packet_type_in_if'][packet_type] = calculate_stats(data)
        avgStates['minimalcell_rx']['rx_rate_per_packet_type_in_if'][packet_type] = calculate_stats(data_rate)

    # RPl 타입 패킷에 대해 따로 계산
    rpl_data = []
    rpl_data_rate = []

    for run_id, stats in allstats.items():
        rpl = 0
        rpl_tx = 0
        if 'DIO' in stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if'] and 'DIO' in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if']:
            rpl += stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if']['DIO']
            rpl_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if']['DIO']

        if 'DIS' in stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if'] and 'DIS' in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if']:
            rpl += stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if']['DIS']
            rpl_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if']['DIS']

        if rpl_tx != 0:
            rpl_data.append(rpl)        
            rpl_data_rate.append(rpl/rpl_tx)
        else:
            rpl_data.append(0)        
            rpl_data_rate.append(0) 


    avgStates['minimalcell_rx']['num_per_packet_type_in_if']['rpl'] = calculate_stats(rpl_data)
    avgStates['minimalcell_rx']['rx_rate_per_packet_type_in_if']['rpl'] = calculate_stats(rpl_data_rate)

 #=========================================================================================================================

    # 비간섭 환경에서 수신 패킷 전체에 패킷별로 평균 계산
    avgStates['minimalcell_rx']['num_per_packet_type_in_no_if'] = {}
    avgStates['minimalcell_rx']['rx_rate_per_packet_type_in_no_if'] = {}

    rcv_packet_type_set = set()
    for run_id, stats in allstats.items():
        rcv_packet_type_set.update(stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if'].keys())

    for packet_type in rcv_packet_type_set:
        data = []
        for run_id, stats in allstats.items():
            if packet_type in stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if'] and packet_type in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']:
                data.append(stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if'][packet_type])
                data_rate.append((stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if'][packet_type])/stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if'][packet_type])
            else:
                data.append(0)
                data_rate.append(0)
        avgStates['minimalcell_rx']['num_per_packet_type_in_no_if'][packet_type] = calculate_stats(data)
        avgStates['minimalcell_rx']['rx_rate_per_packet_type_in_no_if'][packet_type] = calculate_stats(data_rate)

    # RPl 타입 패킷에 대해 따로 계산
    rpl_data = []
    rpl_data_rate = []

    for run_id, stats in allstats.items():
        rpl = 0
        rpl_tx = 0

        if 'DIO' in stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if'] and 'DIO' in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']:
            rpl += stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if']['DIO']
            rpl_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']['DIO']

        if 'DIS' in stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if'] and 'DIS' in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']:
            rpl += stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if']['DIS']
            rpl_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']['DIS']

        if rpl_tx != 0:
            rpl_data.append(rpl)        
            rpl_data_rate.append(rpl/rpl_tx)
        else:
            rpl_data.append(0)        
            rpl_data_rate.append(0) 


    avgStates['minimalcell_rx']['num_per_packet_type_in_no_if']['rpl'] = calculate_stats(rpl_data)
    avgStates['minimalcell_rx']['rx_rate_per_packet_type_in_no_if']['rpl'] = calculate_stats(rpl_data_rate)

 #=========================================================================================================================

    # 네트워크에 싱크된 노드의 평균 개수를 계산함
    sync_motes_num_data = [sum(value == True for value in stats['global-stats']['sync_motes'].values()) for run_id, stats in allstats.items()]
    avgStates['sync_motes_num'] = calculate_stats(sync_motes_num_data)

 #=========================================================================================================================

    # 네트워크에 토폴로지에 참여한 노드의 평균 시간을 계산함
    sync_asn_data = [stats['global-stats']['sync-time'][0]['mean'] for run_id, stats in allstats.items()]
    avgStates['sync_asn']  = calculate_stats(sync_asn_data)

 #=========================================================================================================================

    # 네트워크 토폴로지에 참여한 노드의 평균 개수와 RANK 값의 평균을 계산함
    rpl_motes_num_data = []
    rpl_rank_avg_data = []
    rpl_parent_change_num_avg_data = []
    for (run_id, run_motes) in list(allstats.items()):
        rpl_motes_num = 0
        rpl_rank = []
        rpl_parent_change_num = []

        for (mote_id, motestats) in list(run_motes.items()):
            if 'rpl_join' in motestats:
                if motestats['rpl_join']:
                    rpl_motes_num += 1
                    rpl_rank.append(motestats['rank'])
                    rpl_parent_change_num.append(motestats['rpl_parent_change_num'])

        rpl_motes_num_data.append(rpl_motes_num)
        rpl_rank_avg_data.append(np.mean(rpl_rank))
        rpl_parent_change_num_avg_data.append(np.mean(rpl_parent_change_num))

    avgStates['rpl_motes_num'] = calculate_stats(rpl_motes_num_data)
    avgStates['rpl_rank'] = calculate_stats(rpl_rank_avg_data)
    avgStates['rpl_parent_change_num'] = calculate_stats(rpl_parent_change_num_avg_data)

 #=========================================================================================================================

    # 네트워크에 토폴로지에 참여한 노드의 평균 시간을 계산함
    rpl_asn_data =  [stats['global-stats']['rpl-time'][0]['mean'] for run_id, stats in allstats.items()]
    avgStates['rpl_asn']  = calculate_stats(rpl_asn_data)
    rpl_first_asn_data =  [stats['global-stats']['rpl-first-time'][0]['mean'] for run_id, stats in allstats.items()]
    avgStates['rpl_first_asn']  = calculate_stats(rpl_first_asn_data)

 #=========================================================================================================================

    # 루트 노드를 제외한 노드들의 평균 이웃 개수를 구함
    neighbor_num_avg_data = []
    for (run_id, per_mote_stats) in list(allstats.items()):
        neighbor_num_sum = 0
        num_mote = 0
        for (mote_id, motestats) in list(per_mote_stats.items()):
            if 'neighbor_num' in motestats:
                neighbor_num_sum += motestats['neighbor_num']
                num_mote += 1
        neighbor_num_avg_data.append(neighbor_num_sum/num_mote)
    avgStates['neighbor_num']  =  calculate_stats(neighbor_num_avg_data)

 #=========================================================================================================================

    # 시뮬레이션의 평균 PDR을 계산함
    e2e_upstream_delivery_data = [stats['global-stats']['e2e-upstream-delivery'][0]['value'] for run_id, stats in allstats.items()]
    avgStates['e2e-upstream-delivery']  = calculate_stats(e2e_upstream_delivery_data)

 #=========================================================================================================================

    # 시뮬레이션의 평균 지연시간을 계산함
    e2e_upstream_latency_data = [stats['global-stats']['e2e-upstream-latency'][0]['mean'] for run_id, stats in allstats.items()]
    avgStates['e2e-upstream-latency']  = calculate_stats(e2e_upstream_latency_data)

 #=========================================================================================================================

    # 시뮬레이션의 평균 에너지 소모량을 계산함
    charge_consumed_data = [stats['global-stats']['charge-consumed'][0]['mean'] for run_id, stats in allstats.items()]
    avgStates['charge-consumed']  = calculate_stats(charge_consumed_data)

 #=========================================================================================================================

    # 시뮬레이션의 평균 싱크 전 에너지 소모량을 계산함
    charge_consumed_before_sync_data = [stats['global-stats']['charge-consumed-before-sync'][0]['mean'] for run_id, stats in allstats.items()]
    avgStates['charge-consumed-before-sync']  = calculate_stats(charge_consumed_before_sync_data)

 #=========================================================================================================================

    # 모트당 평균 홉 수를 저장
    avg_hops_data = [stats['global-stats']['avg-hops'][0]['mean'] for run_id, stats in allstats.items()]
    avgStates['avg-hops']  = calculate_stats(avg_hops_data)

 #=========================================================================================================================

    # 모트당 평균 미니멀셀 활용도를 저장
    minimal_cell_utilization_data = [stats['global-stats']['minimal-cell-utilization'][0]['mean'] for run_id, stats in allstats.items()]
    avgStates['minimal-cell-utilization']  = calculate_stats(minimal_cell_utilization_data)

 #=========================================================================================================================
    # 모든 데이터 수집
    filled_data_tx = []
    filled_data_rx = []
    filled_data_neighbor = []
    filled_data_neighbor_rssi_sum = []

    for (run_id, per_mote_stats) in allstats.items():
        for (mote_id, motestats) in per_mote_stats.items():
            if 'num_minimal_cells_tx' in motestats:
                filled_data_tx.append(motestats['num_minimal_cells_tx'])
            if 'num_minimal_cells_rx' in motestats:
                filled_data_rx.append(motestats['num_minimal_cells_rx'])
            if 'neighbor_num_per_minimal_cell' in motestats:
                filled_data_neighbor.append(motestats['neighbor_num_per_minimal_cell'])
            if 'neighbor_rssi_sum' in motestats:
                filled_data_neighbor_rssi_sum.append(motestats['neighbor_rssi_sum'])

    # x 값 설정
    x_values = range(0, 505001, 101)

    # 데이터프레임 생성 및 데이터 채우기
    df = pd.DataFrame({'tx': x_values})

    for i, data in enumerate(filled_data_tx, start=1):
        filled_data_i = fill_missing_values(data, x_values)
        df['Mote {}'.format(i)] = filled_data_i

    # 합계 열 추가
    df['Row Sum'] = df.apply(calculate_row_sum, axis=1)

    # 엑셀 파일로 저장
    writer = pd.ExcelWriter('minimla_cell_congestion.xlsx')
    df.to_excel(writer, sheet_name='num_minimal_cells_tx', index=False)
    writer.save()

    # 데이터프레임 생성 및 데이터 채우기
    df2 = pd.DataFrame({'rx': x_values})

    for i, data in enumerate(filled_data_rx, start=1):
        filled_data_i = fill_missing_values(data, x_values)
        df2['Mote {}'.format(i)] = filled_data_i

    # 합계 열 추가
    df2['Row Sum'] = df2.apply(calculate_row_sum, axis=1)

    # 네트워크 참여 노드의 수 열 추가
    network_node_num = [(row.iloc[1:-1] != 0).sum() for _, row in df2.iterrows()]
    df2['network_node_num'] = network_node_num

    # 엑셀 파일로 저장
    writer = pd.ExcelWriter('minimla_cell_congestion.xlsx', engine='openpyxl', mode='a')
    df2.to_excel(writer, sheet_name='num_minimal_cells_rx', index=False)
    writer.save()

    # 데이터프레임 생성 및 데이터 채우기
    df3 = pd.DataFrame({'neighbor_num': x_values})

    for i, data in enumerate(filled_data_neighbor, start=1):
        filled_data_i = fill_missing_values(data, x_values)
        df3['Mote {}'.format(i)] = filled_data_i

    # 합계 열 추가
    df3['Row Sum'] = df3.apply(calculate_row_sum, axis=1)

    # 엑셀 파일로 저장
    writer = pd.ExcelWriter('minimla_cell_congestion.xlsx', engine='openpyxl', mode='a')
    df3.to_excel(writer, sheet_name='neighbor_num_per_minimal_cell', index=False)
    writer.save()

    # 데이터프레임 생성 및 데이터 채우기
    df4 = pd.DataFrame({'neighbor_rssi_sum': x_values})

    for i, data in enumerate(filled_data_neighbor_rssi_sum, start=1):
        filled_data_i = fill_missing_values(data, x_values)
        df4['Mote {}'.format(i)] = filled_data_i

    # 합계 열 추가
    df4['Row Sum'] = df4.apply(calculate_row_sum, axis=1)

    # 엑셀 파일로 저장
    writer = pd.ExcelWriter('minimla_cell_congestion.xlsx', engine='openpyxl', mode='a')
    df4.to_excel(writer, sheet_name='neighbor_rssi_sum', index=False)
    writer.save()

    # 종합
    df5 = pd.DataFrame({'asn': x_values})
    df5['tx_per_minimal_cell'] = df['Row Sum'] / d.MSF_MAX_MINIMAL_NUMCELLS    # 미니멀셀에서 평균적으로 수신되는 패킷의 수 (노드의 수)
    df5['rx_per_minimal_cell'] = df2['Row Sum'] / d.MSF_MAX_MINIMAL_NUMCELLS   # 미니멀셀에서 평균적으로 송신되는 패킷의 수 (노드의 수)
    df5['rx_per_tx'] =  df5['rx_per_minimal_cell'] / df5['tx_per_minimal_cell'] # 미니멀셀에서 평균적으로 송신당 수신되는 패킷의 수

    df5['neighbor_sum'] = df3['Row Sum']    # 네트워크에 참여한 각 노드의 이웃의 수 합계
    df5['network_node_num'] = df2['network_node_num']   # 네트워크에 참여중인 노드의 수
    df5['neighbor_node_avg'] = df5['neighbor_sum'] / df5['network_node_num']    # 네트워크에 참여중인 노드당 평균 이웃의 수

    df5['neighbor_rssi_sum'] = df4['Row Sum']   # 네트워크에 참여한 각 노드가 자신의 모든 이웃들의 RSSI 합계
    df5['neighbor_rssi_avg'] = df5['neighbor_rssi_sum'] / df5['neighbor_sum']   # 이웃당 평균 RSSI

    # neighbor_sum이 0인 경우를 처리하여 NaN이 아닌 값을 할당
    df5.loc[df5['neighbor_sum'] == 0, 'neighbor_rssi_avg'] = 0
    df5['neighbor_pdr'] = df5['neighbor_rssi_avg'].apply(_rssi_to_pdr)  # 평균 RSSI를 PDR로 변경

    df5['tx_node_among_neighbors'] = df5['tx_per_minimal_cell'] * (df5['neighbor_node_avg'] / df5['network_node_num']) # 이웃들 중 송신하는 노드의 수
    df5['rx_node_among_neighbors'] = df5['neighbor_node_avg'] - df5['tx_node_among_neighbors'] # 이웃들 중 수신하는 노드의 수
    df5['expected_rx_node_num'] = df5['rx_node_among_neighbors'] * df5['neighbor_pdr'] # 링크를 고려한 수신 예상 노드의 수

    df5['alpha']  = df5['expected_rx_node_num'] / df5['rx_per_tx'] # 혼잡도 

    # 엑셀 파일로 저장
    writer = pd.ExcelWriter('minimla_cell_congestion.xlsx', engine='openpyxl', mode='a')
    df5.to_excel(writer, sheet_name='total', index=False)
    writer.save()

 #=========================================================================================================================
    # === remove unnecessary stats

    for (run_id, per_mote_stats) in list(allstats.items()):
        for (mote_id, motestats) in list(per_mote_stats.items()):
            if 'sync_asn' in motestats:
                del motestats['sync_asn']
            if 'charge_asn' in motestats:
                del motestats['charge_asn']
                del motestats['charge']
            if 'join_asn' in motestats:
                del motestats['upstream_pkts']
                del motestats['hops']
                del motestats['join_asn']

    return avgStates, allstats

# 미니멀셀 혼잡도 조사를 위해 데이터를 채워넣는 함수
def fill_missing_values(data, x_values):
    filled_data = [0] * len(x_values)
    prev_x = None
    prev_y = None
    for i, x in enumerate(x_values):
        if x in data:
            prev_x = x
            prev_y = data[x]
        filled_data[i] = prev_y if prev_x is not None else 0
    return filled_data

# 데이터 합계 계산 함수
def calculate_row_sum(row):
    return sum(row[1:])

# 데이터 평균 계산 함수
def calculate_row_mean(row):
    return mean(row[1:])

def calculate_stats(data):
    # 평균 계산
    avg = np.mean(data)
    
    # 표준 편차 계산
    std = np.std(data)

    # 샘플 크기
    num_samples = len(data)

    # 신뢰 구간 계산
    margin_of_error = 1.96 * std / np.sqrt(num_samples) # 1.96은 95% 신뢰 수준에서의 Z 값
    return  {   'mean': avg,
                'std_dev': std,
                'margin_of_error': margin_of_error}

def _rssi_to_pdr(rssi):
    """
    rssi and pdr relationship obtained by experiment below
    http://wsn.eecs.berkeley.edu/connectivity/?dataset=dust
    """

    rssi_pdr_table = {
        -97:    0.0000,  # this value is not from experiment
        -96:    0.1494,
        -95:    0.2340,
        -94:    0.4071,
        # <-- 50% PDR is here, at RSSI=-93.6
        -93:    0.6359,
        -92:    0.6866,
        -91:    0.7476,
        -90:    0.8603,
        -89:    0.8702,
        -88:    0.9324,
        -87:    0.9427,
        -86:    0.9562,
        -85:    0.9611,
        -84:    0.9739,
        -83:    0.9745,
        -82:    0.9844,
        -81:    0.9854,
        -80:    0.9903,
        -79:    1.0000,  # this value is not from experiment
    }

    minRssi = min(rssi_pdr_table.keys())
    maxRssi = max(rssi_pdr_table.keys())

    floorRssi = int(math.floor(rssi))
    if  floorRssi < minRssi:
        pdr = 0.0
    elif floorRssi >= maxRssi:
        pdr = 1.0
    else:
        pdrLow  = rssi_pdr_table[floorRssi]
        pdrHigh = rssi_pdr_table[floorRssi+1]
        # linear interpolation
        pdr = (pdrHigh - pdrLow) * (rssi - float(floorRssi)) + pdrLow

    assert 0 <= pdr <= 1.0

    return pdr
# =========================== main ============================================

def main():

    # FIXME: This logic could be a helper method for other scripts
    # Identify simData having the latest results. That directory should have
    # the latest "mtime".
    subfolders = list(
        [os.path.join('simData', x) for x in os.listdir('simData')]
    )
    subfolder = max(subfolders, key=os.path.getmtime)
    for infile in glob.glob(os.path.join(subfolder, '*.dat')):
        print('generating KPIs for {0}'.format(infile))

        # gather the kpis
        avg, kpis = kpis_all(infile)

        # print on the terminal
        # print(json.dumps(kpis, indent=4))

        # add to the data folder
        outfile = '{0}.kpi'.format(infile)
        with open(outfile, 'w') as f:
            f.write(json.dumps(kpis, indent=4))
        print('KPIs saved in {0}'.format(outfile))

        # 필요한 평균 데이터를 다른 파일에 저장함
        avgoutfile = '{0}_avg.txt'.format(infile)
        with open(avgoutfile, 'w') as f:
            f.write(json.dumps(avg, indent=4))
        print('KPIs saved in {0}'.format(avgoutfile))

        # 평균 데이터를 excel로 저장함
        
        # JSON 데이터를 읽어옴
        with open(avgoutfile, 'r') as file:
            data = json.load(file)

        output_file = avgoutfile + '.csv'

        # 데이터를 평면 구조로 변환
        flattened_data = flatten_dict(data)

        # CSV 파일로 저장
        with open(output_file, 'wb') as csvfile:
            writer = csv.writer(csvfile)
            # 헤더 쓰기
            writer.writerow(['Key', 'Value'])
            # 키-값 쓰기 (정렬된 순서로)
            for key, value in sorted(flattened_data.items()):
                writer.writerow([key, value])
       

# 중첩된 딕셔너리를 평면 구조로 변환하는 재귀 함수
def flatten_dict(d, parent_key='', sep='.'):
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

if __name__ == '__main__':
    main()
