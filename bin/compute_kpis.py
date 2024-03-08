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
        'rpl_time_s' : None,
        'sync_time_s': None,
        'charge_asn': None,
        'upstream_pkts': {},
        'latencies': [],
        'hops': [],
        'charge': None,
        'lifetime_AA_years': None,
        'avg_current_uA': None,
        'neighbor_num': 0,
        'rank' : d.RPL_INFINITE_RANK,
        'rpl_join' : False
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
                and
                (mote_id != DAGROOT_ID)
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

            charge =  logline['idle_listen'] * d.CHARGE_IdleListen_uC
            charge += logline['tx_data_rx_ack'] * d.CHARGE_TxDataRxAck_uC
            charge += logline['rx_data_tx_ack'] * d.CHARGE_RxDataTxAck_uC
            charge += logline['tx_data'] * d.CHARGE_TxData_uC
            charge += logline['rx_data'] * d.CHARGE_RxData_uC
            charge += logline['sleep'] * d.CHARGE_Sleep_uC

            allstats[run_id][mote_id]['charge_asn'] = asn
            allstats[run_id][mote_id]['charge']     = charge

        elif logline['_type'] == SimLog.LOG_USER_MINIMALCELL_PACKETS['type']:
            if 'minimalcell_packets' not in networkStats[run_id]:
                networkStats[run_id]['minimalcell_packets'] = {}

            # 미니멀셀 사용 횟수를 저장한다.
            if 'num_cell_used' not in networkStats[run_id]['minimalcell_packets']:
                networkStats[run_id]['minimalcell_packets']['num_cell_used'] = 1
            else:
                networkStats[run_id]['minimalcell_packets']['num_cell_used'] += 1
    
            # 충돌 여부를 저장할 변수
            collision_detected = False

            # 패킷의 종류가 2개 이상일 경우 충돌이 발생함
            if len(logline['count_per_packet_type']) > 1:
                collision_detected = True                

            # 미니멀셀에서 데이터를 전송한 패킷의 종류와 개수를 저장한다.
            for key, value in logline['count_per_packet_type'].items():
                if 'count_per_packet_type' not in networkStats[run_id]['minimalcell_packets']:
                    networkStats[run_id]['minimalcell_packets']['count_per_packet_type'] = {}

                if 'num_collision_packet' not in networkStats[run_id]['minimalcell_packets']:
                    networkStats[run_id]['minimalcell_packets']['num_collision_packet'] = {}

                # 동시에 전송한 패킷이 2개 이상일 경우 충돌이 발생함
                if value > 1 :
                    collision_detected = True

                # 미니멀 셀에서 전송된 패킷의 수를 타입별로 저장함
                if key not in networkStats[run_id]['minimalcell_packets']['count_per_packet_type']:
                    networkStats[run_id]['minimalcell_packets']['count_per_packet_type'][key] = value
                else:
                    networkStats[run_id]['minimalcell_packets']['count_per_packet_type'][key] += value

                # 간섭이 발생한 환경에서 전송된 패킷 개수를 타입별로 저장함
                if collision_detected:
                    if key not in networkStats[run_id]['minimalcell_packets']['num_collision_packet']:
                        networkStats[run_id]['minimalcell_packets']['num_collision_packet'][key] = value
                    else:
                        networkStats[run_id]['minimalcell_packets']['num_collision_packet'][key] += value

            # 미니멀 셀에서 간섭이 발생한 채널의 개수를 저장함
            if collision_detected:
                if 'num_collision_cell' not in networkStats[run_id]['minimalcell_packets']:
                    networkStats[run_id]['minimalcell_packets']['num_collision_cell'] = 1
                else:
                    networkStats[run_id]['minimalcell_packets']['num_collision_cell'] += 1
    
        # RPL 선호 부모 선택 여부 및 RPL 네트워크 참여 시간을 저장함
        elif logline['_type'] == SimLog.LOG_RPL_CHURN['type']:

            mote_id = logline['_mote_id']
            preferredParent = logline['preferredParent']

            if mote_id == DAGROOT_ID:
                continue
            
            # 변경할 부모의 주소가 있다면, RPL 네트워크에 참여했으며 참여한 시간을 저장한다.
            if preferredParent is None:
                allstats[run_id][mote_id]['rpl_join'] = False
            else :
                allstats[run_id][mote_id]['rpl_join'] = True
                allstats[run_id][mote_id]['rpl_asn']  = asn
                allstats[run_id][mote_id]['rpl_time_s'] = asn*file_settings['tsch_slotDuration']

        # 미니멀 셀에서 전송된 패킷의 수신 결과를 저장함
        elif logline['_type'] == SimLog.LOG_USER_MINIMALCELL_TRANS_RESULT['type']:

            if 'minimalcell_trans_result' not in networkStats[run_id]:
                networkStats[run_id]['minimalcell_trans_result'] = {}
            if 'count_per_packet_type' not in networkStats[run_id]['minimalcell_trans_result']:
                networkStats[run_id]['minimalcell_trans_result']['count_per_packet_type'] = {}

            txResults = logline['txResults']
            
            for txResult in txResults:

                is_interference = txResult['is_interference']
                is_recv_success = txResult['is_recv_success']
                packet_type = txResult['count_per_packet_type']

                if 'no_if_fail' not in networkStats[run_id]['minimalcell_trans_result']:
                    networkStats[run_id]['minimalcell_trans_result']['no_if_fail'] = 0
                if 'if_fail' not in networkStats[run_id]['minimalcell_trans_result']:
                    networkStats[run_id]['minimalcell_trans_result']['if_fail'] = 0
                if 'no_if_success' not in networkStats[run_id]['minimalcell_trans_result']:
                    networkStats[run_id]['minimalcell_trans_result']['no_if_success'] = 0
                if 'if_success' not in networkStats[run_id]['minimalcell_trans_result']:
                    networkStats[run_id]['minimalcell_trans_result']['if_success'] = 0

                # 간섭 발생 여부와 패킷을 정상적으로 수신했는지 정리함
                if is_interference == False and is_recv_success == False:
                    networkStats[run_id]['minimalcell_trans_result']['no_if_fail'] += 1
                elif is_interference == True and is_recv_success == False:
                    networkStats[run_id]['minimalcell_trans_result']['if_fail'] += 1
                elif is_interference == False and is_recv_success == True:
                    networkStats[run_id]['minimalcell_trans_result']['no_if_success'] += 1
                else:
                    networkStats[run_id]['minimalcell_trans_result']['if_success'] += 1

                # 수신된 패킷을 종류별로 저장한다.
                if is_recv_success:
                    if packet_type not in networkStats[run_id]['minimalcell_trans_result']['count_per_packet_type']:
                        networkStats[run_id]['minimalcell_trans_result']['count_per_packet_type'][packet_type] = 0
                    else:
                        networkStats[run_id]['minimalcell_trans_result']['count_per_packet_type'][packet_type] += 1

        # 장치별 이웃 수를 저장함
        elif logline['_type'] == SimLog.LOG_USER_NEIGHBOR_NUM['type']:

            mote_id = logline['_mote_id']
            neighbor_num = logline['neighbor_num']

            if mote_id == DAGROOT_ID:
                continue

            allstats[run_id][mote_id]['neighbor_num'] = neighbor_num
        
        # 장치별 RPL Rank 값을 저장함
        elif logline['_type'] == SimLog.LOG_USER_RPL_RANK['type']:
            
            mote_id = logline['_mote_id']
            rank = logline['rank']

            if mote_id == DAGROOT_ID or rank is None:
                continue
            
            allstats[run_id][mote_id]['rank'] = rank

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
        sync_times = []
        us_latencies = []
        current_consumed = []
        lifetimes = []
        slot_duration = file_settings['tsch_slotDuration']

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

            # latency

            us_latencies += motestats['latencies']

            # current consumed

            current_consumed.append(motestats['charge'])
            if motestats['lifetime_AA_years'] is not None:
                lifetimes.append(motestats['lifetime_AA_years'])
            current_consumed = [
                value for value in current_consumed if value is not None
            ]

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
            'current-consumed': [
                {
                    'name': 'Current Consumed',
                    'unit': 'mA',
                    'mean': (
                        mean(current_consumed)
                        if current_consumed else 'N/A'
                    ),
                    '99%': (
                        np.percentile(current_consumed, 99)
                        if current_consumed else 'N/A'
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
            ]
        }

        # 실험을 위해 저장한 정보를 allstats에 이관함
        allstats[run_id]['global-stats']['minimalcell_packets'] = networkStats[run_id]['minimalcell_packets']
        allstats[run_id]['global-stats']['sync_motes'] = networkStats[run_id]['sync_motes']
        allstats[run_id]['global-stats']['minimalcell_trans_result'] = networkStats[run_id]['minimalcell_trans_result']

    #---------------------평균 계산---------------------
    avgStates = {}
    num_runs = len(allstats)

    # num_cell_used 평균 계산
    avgStates['minimalcell_packets'] = {}
    avg_num_cell_used = sum(stats['global-stats']['minimalcell_packets']['num_cell_used'] for run_id, stats in allstats.items()) / num_runs
    avgStates['minimalcell_packets']['num_cell_used'] = avg_num_cell_used

    # count_per_packet_type의 경우 각 유형에 대한 평균 계산
    avgStates['minimalcell_packets']['count_per_packet_type'] = {}
    packet_type_set = set()
    for run_id, stats in allstats.items():
        packet_type_set.update(stats['global-stats']['minimalcell_packets']['count_per_packet_type'].keys())

    for packet_type in packet_type_set:
        total_count = 0
        for run_id, stats in allstats.items():
            if packet_type in stats['global-stats']['minimalcell_packets']['count_per_packet_type']:
                total_count += stats['global-stats']['minimalcell_packets']['count_per_packet_type'][packet_type]
        avgStates['minimalcell_packets']['count_per_packet_type'][packet_type] = total_count / num_runs

    # num_collision_packet 평균 계산
    avgStates['minimalcell_packets']['num_collision_packet'] = {}
    packet_type_set = set()
    for run_id, stats in allstats.items():
        packet_type_set.update(stats['global-stats']['minimalcell_packets']['num_collision_packet'].keys())

    for packet_type in packet_type_set:
        total_count = 0
        for run_id, stats in allstats.items():
            if packet_type in stats['global-stats']['minimalcell_packets']['num_collision_packet']:
                total_count += stats['global-stats']['minimalcell_packets']['num_collision_packet'][packet_type]
        avgStates['minimalcell_packets']['num_collision_packet'][packet_type] = total_count / num_runs


    # num_collision_cell 평균 계산
    avgStates['minimalcell_packets']['num_collision_cell'] = {}
    avgStates['minimalcell_packets']['num_collision_cell'] = sum(stats['global-stats']['minimalcell_packets']['num_collision_cell'] for run_id, stats in allstats.items()) / num_runs

    # 미니멀셀에서 간섭이 일어났는지에 대한 여부와 전송 결과의 평균을 계산함
    avgStates['minimalcell_trans_result'] = {}
    avgStates['minimalcell_trans_result']['no_if_fail'] = sum(stats['global-stats']['minimalcell_trans_result']['no_if_fail'] for run_id, stats in allstats.items()) / num_runs
    avgStates['minimalcell_trans_result']['if_fail'] = sum(stats['global-stats']['minimalcell_trans_result']['if_fail'] for run_id, stats in allstats.items()) / num_runs
    avgStates['minimalcell_trans_result']['no_if_success'] = sum(stats['global-stats']['minimalcell_trans_result']['no_if_success'] for run_id, stats in allstats.items()) / num_runs
    avgStates['minimalcell_trans_result']['if_success'] = sum(stats['global-stats']['minimalcell_trans_result']['if_success'] for run_id, stats in allstats.items()) / num_runs

    # 수신된 패킷의 평균 계산
    avgStates['minimalcell_trans_result']['count_per_packet_type'] = {}
    rcv_packet_type_set = set()
    for run_id, stats in allstats.items():
        rcv_packet_type_set.update(stats['global-stats']['minimalcell_trans_result']['count_per_packet_type'].keys())

    for packet_type in rcv_packet_type_set:
        total_count = 0
        for run_id, stats in allstats.items():
            if packet_type in stats['global-stats']['minimalcell_trans_result']['count_per_packet_type']:
                total_count += stats['global-stats']['minimalcell_trans_result']['count_per_packet_type'][packet_type]
        avgStates['minimalcell_trans_result']['count_per_packet_type'][packet_type] = total_count / num_runs

    # 네트워크에 싱크된 노드의 평균 개수를 계산함
    avgStates['num_sync_motes'] = sum(sum(value == True for value in stats['global-stats']['sync_motes'].values()) for stats in allstats.values()) / num_runs

    # 네트워크에 토폴로지에 참여한 노드의 평균 시간을 계산함
    avgStates['asn_sync_motes']  = sum(stats['global-stats']['sync-time'][0]['mean'] for run_id, stats in allstats.items()) / num_runs

    # 네트워크 토폴로지에 참여한 노드의 평균 개수와 RANK 값의 평균을 계산함
    rpl_num_sum = 0
    rpl_rank_avg_sum = 0
    for (run_id, run_motes) in list(allstats.items()):
        rpl_rank_sum = 0
        mote_num = 0
        for (mote_id, motestats) in list(run_motes.items()):
            if 'rpl_join' in motestats:
                if motestats['rpl_join']:
                    rpl_num_sum += 1
                mote_num += 1
                if motestats['rank']:
                    rpl_rank_sum += motestats['rank']
        rpl_rank_avg_sum += rpl_rank_sum / mote_num
    avgStates['num_rpl_motes']  =   rpl_num_sum / num_runs
    avgStates['rpl_rank']  =   rpl_rank_avg_sum / num_runs

    # 네트워크에 토폴로지에 참여한 노드의 평균 시간을 계산함
    avgStates['asn_rpl_motes']  = sum(stats['global-stats']['rpl-time'][0]['mean'] for run_id, stats in allstats.items()) / num_runs

    # 루트 노드를 제외한 노드들의 평균 이웃 개수를 구함
    neighbor_num_avg_sum = 0
    for (run_id, per_mote_stats) in list(allstats.items()):
        neighbor_num_sum = 0
        num_mote = 0
        for (mote_id, motestats) in list(per_mote_stats.items()):
            if 'neighbor_num' in motestats:
                neighbor_num_sum += motestats['neighbor_num']
                num_mote += 1
        neighbor_num_avg_sum += neighbor_num_sum/num_mote
    avgStates['neighbor_num']  =  neighbor_num_avg_sum / num_runs

    # 시뮬레이션의 평균 PDR을 계산함
    avgStates['e2e-upstream-delivery']  = sum(stats['global-stats']['e2e-upstream-delivery'][0]['value'] for run_id, stats in allstats.items()) / num_runs

    # 시뮬레이션의 평균 지연시간을 계산함
    avgStates['e2e-upstream-latency']  = sum(stats['global-stats']['e2e-upstream-latency'][0]['mean'] for run_id, stats in allstats.items()) / num_runs

    # 시뮬레이션의 평균 에너지 소모량을 계산함
    avgStates['current-consumed']  = sum(stats['global-stats']['current-consumed'][0]['mean'] for run_id, stats in allstats.items()) / num_runs

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
