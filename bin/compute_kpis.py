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
from collections import Counter

import datetime
from SimEngine import SimLog
import SimEngine.Mote.MoteDefines as d

# =========================== defines =========================================

DAGROOT_ID = 0  # we assume first mote is DAGRoot
DAGROOT_IP = 'fd00::1:0'
BATTERY_AA_CAPACITY_mAh = 2821.5

# =========================== decorators ======================================

def openfile(func):
    def inner(inputfile, *args, **kwargs):
        with open(inputfile, 'r') as f:
            return func(f, *args, **kwargs)
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
        'sync_asn': [],
        'rpl_asn' : None,
        'rpl_asn_total' : [],
        'rpl_first_asn' : None,
        'rpl_parent_change_num' : None,
        'rpl_parent_change_num_total' : None,
        'rpl_time_s' : None,
        'rpl_parent_id' : None,
        'sync_time_s': None,
        'charge_asn': None,
        'charge_asn_before_sync': None,
        'upstream_pkts': {},
        'latencies': [],
        'hops': [],
        'charge': 0,
        'charge_before_sync': 0,
        'lifetime_AA_years': None,
        'avg_current_uA': None,
        'neighbor_num': 0,
        'rank' : [],
        'rpl_join' : False,
        'avg_hops' : None,
        'last_hops' : None,
        'num_minimal_cells_rx' : {},
        'num_minimal_cells_tx' : {},
        'minimal_cell_utilization' : {},
        'neighbor_num_per_minimal_cell' : {},
        'neighbor_rssi_sum' : {},
        'network_nodes_num' : {},
        'minimal_cell_chan_seq' : {},
        'received_dio_id_list' : [], 
        'received_dio_parent_id_list' : [],
        'received_dio_rank_list' : {},
        'received_dio_rank_list_after_sync' : {},
        'desync_asn' : [],
        'desync_code' : {},
        'desync_child_ids' : [],
        'desync_child_router_ids': [],
        'desync_router_num' : 0,
        'keep_alive_asn' : [],
        'keep_alive_acked' : [],
        'autonomous_tx_acked_jrq' : {},
        'autonomous_tx_acked_6p' : {},
        'autonomous_tx_acked_kp' : {},
        'autonomous_tx_acked' : [],
        'dio_tx_num' : {},
        'packets_by_type_tx' : {},
        'packets_by_type_rx' : {},
        'add_cell_asn' : []
    }

# =========================== KPIs ============================================

@openfile
def kpis_all(inputfile, subfolder):

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
            if mote_id == 0:
                allstats[run_id][mote_id]['sync_asn'].append(0)

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

            allstats[run_id][mote_id]['sync_asn'].append(asn)
            allstats[run_id][mote_id]['sync_time_s'] = asn*file_settings['tsch_slotDuration']

        elif logline['_type'] == SimLog.LOG_TSCH_DESYNCED['type']:

            # shorthands
            mote_id    = logline['_mote_id']
            code   = logline['code']
            child_ids = logline['child_ids']
            child_router_ids = logline['child_router_ids']

            # only log non-dagRoot sync times
            if mote_id == DAGROOT_ID:
                continue

            # 비동기화된 모트들을 삭제함
            networkStats[run_id]['sync_motes'][mote_id] = False
            allstats[run_id][mote_id]['desync_asn'].append(asn)

            # 해당 code가 desync_code 딕셔너리에 없다면 초기화
            if code not in allstats[run_id][mote_id]['desync_code']:
                allstats[run_id][mote_id]['desync_code'][code] = []

            # 해당 code에 asn 값을 추가
            allstats[run_id][mote_id]['desync_code'][code].append(asn)

            # 디싱크 시 중계 노드가 아닌 자식의 개수 저장
            allstats[run_id][mote_id]['desync_child_ids'].append(child_ids)

            # 디싱크 시 중계 노드인 아닌 자식의 개수 저장
            allstats[run_id][mote_id]['desync_child_router_ids'].append(child_router_ids)

            # 중계 노드의 Desync 횟수 저장
            if len(child_ids) != 0:
                allstats[run_id][mote_id]['desync_router_num'] += 1

            # RPL에 참여했던 부분도 삭제함
            allstats[run_id][mote_id]['rpl_join'] = False
            allstats[run_id][mote_id]['rpl_asn']  = None
            allstats[run_id][mote_id]['rpl_first_asn'] = None
            allstats[run_id][mote_id]['received_dio_rank_list_after_sync'] = {}
            allstats[run_id][mote_id]['rpl_parent_id'] = None
            allstats[run_id][mote_id]['rpl_parent_change_num'] = None

        elif logline['_type'] == SimLog.LOG_TSCH_TXDONE['type']:
            # shorthands
            mote_id    = logline['_mote_id']
            packet     = logline['packet']
            isAutonomousTx  = logline['isAutonomousTx']
            isACKed  = logline['isACKed']
            packet_type = logline['packet']['type']  # 패킷 타입

            if packet[u'type'] == d.PKT_TYPE_KEEP_ALIVE:
                allstats[run_id][mote_id]['keep_alive_asn'].append(asn) 

                if not isAutonomousTx:
                    allstats[run_id][mote_id]['keep_alive_acked'].append(isACKed) 

            if isAutonomousTx:
                allstats[run_id][mote_id]['autonomous_tx_acked'].append(isACKed)
                if packet[u'type'] == d.PKT_TYPE_JOIN_REQUEST:
                    # 딕셔너리로 ASN을 키로 하고, ACK 수신 여부를 값으로 저장
                    if 'autonomous_tx_acked_jrq' not in allstats[run_id][mote_id]:
                        allstats[run_id][mote_id]['autonomous_tx_acked_jrq'] = {}
                    allstats[run_id][mote_id]['autonomous_tx_acked_jrq'][asn] = isACKed

                elif packet[u'type'] == d.PKT_TYPE_SIXP:
                    if 'autonomous_tx_acked_6p' not in allstats[run_id][mote_id]:
                        allstats[run_id][mote_id]['autonomous_tx_acked_6p'] = {}
                    allstats[run_id][mote_id]['autonomous_tx_acked_6p'][asn] = isACKed

                elif packet[u'type'] == d.PKT_TYPE_KEEP_ALIVE:
                    if 'autonomous_tx_acked_kp' not in allstats[run_id][mote_id]:
                        allstats[run_id][mote_id]['autonomous_tx_acked_kp'] = {}
                    allstats[run_id][mote_id]['autonomous_tx_acked_kp'][asn] = isACKed

            # 패킷 타입별로 데이터를 저장할 구조가 없으면 생성
            if 'packets_by_type_tx' not in allstats[run_id][mote_id]:
                allstats[run_id][mote_id]['packets_by_type_tx'] = {}

            # 패킷 타입에 해당하는 데이터가 없다면 생성
            if packet_type not in allstats[run_id][mote_id]['packets_by_type_tx']:
                allstats[run_id][mote_id]['packets_by_type_tx'][packet_type] = []

            allstats[run_id][mote_id]['packets_by_type_tx'][packet_type].append(asn)

        elif logline['_type'] == SimLog.LOG_TSCH_RXDONE['type']:
            # shorthands
            mote_id = logline['_mote_id']
            packet_type = logline['packet']['type']  # 패킷 타입
            is_clock_source = logline['is_clock_source']  # 클럭 소스 여부

            # 패킷 타입별로 데이터를 저장할 구조가 없으면 생성
            if 'packets_by_type_rx' not in allstats[run_id][mote_id]:
                allstats[run_id][mote_id]['packets_by_type_rx'] = {}

            # 패킷 타입에 해당하는 데이터가 없다면 생성
            if packet_type not in allstats[run_id][mote_id]['packets_by_type_rx']:
                allstats[run_id][mote_id]['packets_by_type_rx'][packet_type] = {
                    'clock_source': [],
                    'non_clock_source': []
                }

            if is_clock_source:
                allstats[run_id][mote_id]['packets_by_type_rx'][packet_type]['clock_source'].append(asn)
            else:
                allstats[run_id][mote_id]['packets_by_type_rx'][packet_type]['non_clock_source'].append(asn)

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
            allstats[run_id][mote_id]['charge']     += charge

            # 싱크 전 에너지 소모량
            is_sync = logline['is_sync']

            if not is_sync:
                charge_before_sync =  logline['idle_listen'] * d.CHARGE_IdleListen_uC
                charge_before_sync += logline['tx_data_rx_ack'] * d.CHARGE_TxDataRxAck_uC
                charge_before_sync += logline['rx_data_tx_ack'] * d.CHARGE_RxDataTxAck_uC
                charge_before_sync += logline['tx_data'] * d.CHARGE_TxData_uC
                charge_before_sync += logline['rx_data'] * d.CHARGE_RxData_uC
                charge_before_sync += logline['sleep'] * d.CHARGE_Sleep_uC

                allstats[run_id][mote_id]['charge_asn_before_syn'] = asn
                allstats[run_id][mote_id]['charge_before_sync']    += charge_before_sync

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
            # 부모 변경 시 받은 DIO Rank인데 어디써야할지 모르겠음
            rank = logline['parent_dio_rank']

            preferred_parent_id = None
            if preferredParent is not None:
                preferred_parent_mac_addr = preferredParent
                cleaned_hex_string = preferred_parent_mac_addr.replace('-', '')
                last_four_hex = cleaned_hex_string[-4:]
                preferred_parent_id = int(last_four_hex, 16)

            if mote_id == DAGROOT_ID:
                continue
            
            # 변경할 부모의 주소가 있다면, RPL 네트워크에 참여했으며 참여한 시간을 저장한다.
            if preferredParent is None:
                allstats[run_id][mote_id]['rpl_join'] = False
                allstats[run_id][mote_id]['rpl_asn']  = None
                allstats[run_id][mote_id]['rpl_first_asn'] = None
                allstats[run_id][mote_id]['rpl_parent_id'] = None
            else :
                # 첫번째 부모 선택 시간을 따로 저장한다.
                if allstats[run_id][mote_id]['rpl_asn'] is None:
                    allstats[run_id][mote_id]['rpl_first_asn'] = asn

                if allstats[run_id][mote_id]['rpl_parent_change_num'] is None:
                    allstats[run_id][mote_id]['rpl_parent_change_num'] = 1
                else:
                    allstats[run_id][mote_id]['rpl_parent_change_num'] += 1

                if allstats[run_id][mote_id]['rpl_parent_change_num_total'] is None:
                    allstats[run_id][mote_id]['rpl_parent_change_num_total'] = 1
                else:
                    allstats[run_id][mote_id]['rpl_parent_change_num_total'] += 1

                allstats[run_id][mote_id]['rpl_join'] = True
                allstats[run_id][mote_id]['rpl_asn']  = asn
                allstats[run_id][mote_id]['rpl_asn_total'].append(asn)
                allstats[run_id][mote_id]['rpl_time_s'] = asn*file_settings['tsch_slotDuration']
                allstats[run_id][mote_id]['rpl_parent_id'] = preferred_parent_id

        # 모든 DIO 수신 내역에 대해 저장함
        elif logline['_type'] == SimLog.LOG_RPL_DIO_RX['type']:
            
            mote_id = logline['_mote_id']
            src_id = logline['src_id']
            is_preferred_parent = logline['is_preferred_parent']
            rank = logline['rank']

            # 모든 DIO 수신 시 송신자 아이디 저장
            allstats[run_id][mote_id]['received_dio_id_list'].append(src_id)

            # 부모에게 받았을 경우 따로 저장
            if is_preferred_parent:
                allstats[run_id][mote_id]['received_dio_parent_id_list'].append(src_id)

            allstats[run_id][mote_id]['received_dio_rank_list'][src_id] = rank
            allstats[run_id][mote_id]['received_dio_rank_list_after_sync'][src_id] = rank
        # 미니멀 셀에서 전송된 패킷의 송신 결과를 저장함
        elif logline['_type'] == SimLog.LOG_RPL_DIO_TX['type']:
            
            mote_id = logline['_mote_id']
            hops = logline['hops']

            minitues = asn * file_settings['tsch_slotDuration'] // 60

            if minitues not in allstats[run_id][mote_id]['dio_tx_num']:
                allstats[run_id][mote_id]['dio_tx_num'][minitues] = {}

            if hops not in allstats[run_id][mote_id]['dio_tx_num'][minitues]:
                allstats[run_id][mote_id]['dio_tx_num'][minitues][hops] = 0

            allstats[run_id][mote_id]['dio_tx_num'][minitues][hops] += 1

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
        
        # 장치별 자신의 RPL Rank 값을 저장함
        elif logline['_type'] == SimLog.LOG_USER_RPL_RANK['type']:
            
            mote_id = logline['_mote_id']
            rank = logline['rank']

            if mote_id == DAGROOT_ID or rank is None:
                continue

            allstats[run_id][mote_id]['rank'].append(rank)
        elif logline['_type'] == SimLog.LOG_USER_MINIMAL_CELL_CONGESTION['type']:
 
            mote_id = logline['_mote_id']
            minimal_cell_asn = logline['minimal_cell_asn']
            num_minimal_cells_rx =  logline['num_minimal_cells_rx']
            num_minimal_cells_tx =  logline['num_minimal_cells_tx']
            minimal_cell_utilization = logline['minimal_cell_utilization']
            neighbor_num = logline['neighbor_num']
            neighbor_rssi_sum = logline['neighbor_rssi_sum']
            network_nodes_num = logline['network_nodes_num']
            minimal_cell_chan_seq = logline['minimal_cell_chan_seq']

            allstats[run_id][mote_id]['num_minimal_cells_rx'][minimal_cell_asn] = num_minimal_cells_rx
            allstats[run_id][mote_id]['num_minimal_cells_tx'][minimal_cell_asn] = num_minimal_cells_tx
            allstats[run_id][mote_id]['minimal_cell_utilization'][minimal_cell_asn] = minimal_cell_utilization
            allstats[run_id][mote_id]['neighbor_num_per_minimal_cell'][minimal_cell_asn] = neighbor_num
            allstats[run_id][mote_id]['neighbor_rssi_sum'][minimal_cell_asn] = neighbor_rssi_sum
            allstats[run_id][mote_id]['network_nodes_num'][minimal_cell_asn] = network_nodes_num
            allstats[run_id][mote_id]['minimal_cell_chan_seq'][minimal_cell_asn] = minimal_cell_chan_seq
        elif logline['_type'] == SimLog.LOG_TSCH_ADD_CELL['type']:

            mote_id = logline['_mote_id']
            cellOptions = logline['cellOptions']

            if 'TX' in cellOptions and 'SHARED' not in cellOptions:
                allstats[run_id][mote_id]['add_cell_asn'].append(asn)

    # === compute advanced motestats

    for (run_id, per_mote_stats) in list(allstats.items()):
        for (mote_id, motestats) in list(per_mote_stats.items()):
            if mote_id != 0:

                if (len(motestats['sync_asn']) != 0) and (motestats['charge_asn'] is not None):
                    # avg_current, lifetime_AA
                    if (
                            (motestats['charge'] <= 0)
                            or
                            (motestats['charge_asn'] <= motestats['sync_asn'][-1])
                        ):
                        motestats['lifetime_AA_years'] = 'N/A'
                    else:
                        motestats['avg_current_uA'] = motestats['charge']/float((motestats['charge_asn']-motestats['sync_asn'][-1]) * file_settings['tsch_slotDuration'])
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
                        motestats['last_hops'] = motestats['hops'][-1]

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

            if len(motestats['sync_asn']) != 0:
                sync_times.append(motestats['sync_asn'][-1])

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
            total_sum = 0
            count = 0
            for cell_utilization_list in motestats["minimal_cell_utilization"].values():
                for cell_utilization in cell_utilization_list:
                    total_sum += cell_utilization
                    count += 1

            # 평균을 계산합니다.
            if count != 0:
                average = total_sum / count
                minimal_cell_utilization.append(average)
            else:
                minimal_cell_utilization.append(0)

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
    num_collision_cell_data = []
    for run_id, stats in allstats.items():
        # 각 실행의 통계 데이터에서 'num_collision_cell' 값을 가져옴
        if 'num_collision_cell' in stats['global-stats']['minimalcell_tx']:
            num_collision_cell_value = stats['global-stats']['minimalcell_tx']['num_collision_cell']
            # 가져온 값을 리스트에 추가
            num_collision_cell_data.append(num_collision_cell_value)

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

    # 전체 패킷과 RPl 타입에 대해 따로 계산
    total_rx_list = []
    total_rate_list = []
    rpl_rx_list = []
    rpl_rate_list = []

    for run_id, stats in allstats.items():
        total_rx = 0
        total_tx = 0
        rpl_rx = 0
        rpl_tx = 0

        if 'DIO' in stats['global-stats']['minimalcell_rx']['num_per_packet_type'] and 'DIO' in stats['global-stats']['minimalcell_tx']['num_per_packet_type']:
            total_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type']['DIO']
            total_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type']['DIO']
            rpl_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type']['DIO']
            rpl_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type']['DIO']

        if 'DIS' in stats['global-stats']['minimalcell_rx']['num_per_packet_type'] and 'DIS' in stats['global-stats']['minimalcell_tx']['num_per_packet_type']:
            total_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type']['DIS']
            total_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type']['DIS']
            rpl_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type']['DIS']
            rpl_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type']['DIS']

        if 'EB' in stats['global-stats']['minimalcell_rx']['num_per_packet_type'] and 'EB' in stats['global-stats']['minimalcell_tx']['num_per_packet_type']:
            total_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type']['EB']
            total_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type']['EB']

        if total_rx != 0:
            total_rx_list.append(total_rx)        
            total_rate_list.append(total_rx/total_tx)
        else:
            total_rx_list.append(0)        
            total_rate_list.append(0) 

        if rpl_tx != 0:
            rpl_rx_list.append(rpl_rx)        
            rpl_rate_list.append(rpl_rx/rpl_tx)
        else:
            rpl_rx_list.append(0)        
            rpl_rate_list.append(0) 

    avgStates['minimalcell_rx']['num_per_packet_type']['total'] = calculate_stats(total_rx_list)
    avgStates['minimalcell_rx']['rx_rate_per_packet_type']['total'] = calculate_stats(total_rate_list)
    
    avgStates['minimalcell_rx']['num_per_packet_type']['rpl'] = calculate_stats(rpl_rx_list)
    avgStates['minimalcell_rx']['rx_rate_per_packet_type']['rpl'] = calculate_stats(rpl_rate_list)

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

    # 전체 패킷과 RPl 타입에 대해 따로 계산
    total_rx_list = []
    total_rate_list = []
    rpl_rx_list = []
    rpl_rate_list = []

    for run_id, stats in allstats.items():
        total_rx = 0
        total_tx = 0
        rpl_rx = 0
        rpl_tx = 0

        if 'DIO' in stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if'] and 'DIO' in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if']:
            total_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if']['DIO']
            total_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if']['DIO']
            rpl_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if']['DIO']
            rpl_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if']['DIO']

        if 'DIS' in stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if'] and 'DIS' in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if']:
            total_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if']['DIS']
            total_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if']['DIS']
            rpl_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if']['DIS']
            rpl_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if']['DIS']

        if 'EB' in stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if'] and 'EB' in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if']:
            total_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_if']['EB']
            total_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_if']['EB']

        if total_rx != 0:
            total_rx_list.append(total_rx)        
            total_rate_list.append(total_rx/total_tx)
        else:
            total_rx_list.append(0)        
            total_rate_list.append(0) 

        if rpl_tx != 0:
            rpl_rx_list.append(rpl_rx)        
            rpl_rate_list.append(rpl_rx/rpl_tx)
        else:
            rpl_rx_list.append(0)        
            rpl_rate_list.append(0) 

    avgStates['minimalcell_rx']['num_per_packet_type_in_if']['total'] = calculate_stats(total_rx_list)
    avgStates['minimalcell_rx']['rx_rate_per_packet_type_in_if']['total'] = calculate_stats(total_rate_list)
    
    avgStates['minimalcell_rx']['num_per_packet_type_in_if']['rpl'] = calculate_stats(rpl_rx_list)
    avgStates['minimalcell_rx']['rx_rate_per_packet_type_in_if']['rpl'] = calculate_stats(rpl_rate_list)

 #=========================================================================================================================

    # 비간섭 환경에서 수신 패킷 전체에 패킷별로 평균 계산
    avgStates['minimalcell_rx']['num_per_packet_type_in_no_if'] = {}
    avgStates['minimalcell_rx']['rx_rate_per_packet_type_in_no_if'] = {}

    rcv_packet_type_set = set()
    for run_id, stats in allstats.items():
        rcv_packet_type_set.update(stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if'].keys())

    for packet_type in rcv_packet_type_set:
        data = []
        data_rate = []
        for run_id, stats in allstats.items():
            if packet_type in stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if'] and packet_type in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']:
                data.append(stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if'][packet_type])
                data_rate.append((stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if'][packet_type])/stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if'][packet_type])
            else:
                data.append(0)
                data_rate.append(0)
        avgStates['minimalcell_rx']['num_per_packet_type_in_no_if'][packet_type] = calculate_stats(data)
        avgStates['minimalcell_rx']['rx_rate_per_packet_type_in_no_if'][packet_type] = calculate_stats(data_rate)

    # 전체 패킷과 RPl 타입에 대해 따로 계산
    total_rx_list = []
    total_rate_list = []
    rpl_rx_list = []
    rpl_rate_list = []

    for run_id, stats in allstats.items():
        total_rx = 0
        total_tx = 0
        rpl_rx = 0
        rpl_tx = 0

        if 'DIO' in stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if'] and 'DIO' in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']:
            total_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if']['DIO']
            total_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']['DIO']
            rpl_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if']['DIO']
            rpl_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']['DIO']

        if 'DIS' in stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if'] and 'DIS' in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']:
            total_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if']['DIS']
            total_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']['DIS']
            rpl_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if']['DIS']
            rpl_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']['DIS']

        if 'EB' in stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if'] and 'EB' in stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']:
            total_rx += stats['global-stats']['minimalcell_rx']['num_per_packet_type_in_no_if']['EB']
            total_tx += stats['global-stats']['minimalcell_tx']['num_per_packet_type_in_no_if']['EB']

        if total_rx != 0:
            total_rx_list.append(total_rx)        
            total_rate_list.append(total_rx/total_tx)
        else:
            total_rx_list.append(0)        
            total_rate_list.append(0) 

        if rpl_tx != 0:
            rpl_rx_list.append(rpl_rx)        
            rpl_rate_list.append(rpl_rx/rpl_tx)
        else:
            rpl_rx_list.append(0)        
            rpl_rate_list.append(0) 

    avgStates['minimalcell_rx']['num_per_packet_type_in_no_if']['total'] = calculate_stats(total_rx_list)
    avgStates['minimalcell_rx']['rx_rate_per_packet_type_in_no_if']['total'] = calculate_stats(total_rate_list)
    
    avgStates['minimalcell_rx']['num_per_packet_type_in_no_if']['rpl'] = calculate_stats(rpl_rx_list)
    avgStates['minimalcell_rx']['rx_rate_per_packet_type_in_no_if']['rpl'] = calculate_stats(rpl_rate_list)

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
    rpl_parent_change_num_total_avg_data = []

    for (run_id, run_motes) in list(allstats.items()):
        rpl_motes_num = 0
        rpl_rank = []
        rpl_parent_change_num = []
        rpl_parent_change_num_total = []

        for (mote_id, motestats) in list(run_motes.items()):
            if 'rpl_join' in motestats:
                if motestats['rpl_join']:
                    rpl_motes_num += 1
                    rpl_rank.append(motestats['rank'][-1])
                    rpl_parent_change_num.append(motestats['rpl_parent_change_num'])
                    rpl_parent_change_num_total.append(motestats['rpl_parent_change_num_total'])

        rpl_motes_num_data.append(rpl_motes_num)
        rpl_rank_avg_data.append(np.mean(rpl_rank))
        rpl_parent_change_num_avg_data.append(np.mean(rpl_parent_change_num))
        rpl_parent_change_num_total_avg_data.append(np.mean(rpl_parent_change_num_total))

    avgStates['rpl_motes_num'] = calculate_stats(rpl_motes_num_data)
    avgStates['rpl_rank'] = calculate_stats(rpl_rank_avg_data)
    avgStates['rpl_parent_change_num'] = calculate_stats(rpl_parent_change_num_avg_data)
    avgStates['rpl_parent_change_num_total'] = calculate_stats(rpl_parent_change_num_total_avg_data)

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

    # 부모로부터 DIO를 수신한 횟수를 구함
    received_dio_parent_id_num_avg_data = []
    for run_id, per_mote_stats in allstats.items():
        received_dio_parent_id_num_sum = 0
        num_mote = 0
        for mote_id, motestats in per_mote_stats.items():
            if 'received_dio_parent_id_list' in motestats:
                received_dio_parent_id_num_sum += len(motestats['received_dio_parent_id_list'])
                num_mote += 1
        received_dio_parent_id_num_avg_data.append(received_dio_parent_id_num_sum / num_mote)

    avgStates['rpl_received_dio_num_from_parent'] = calculate_stats(received_dio_parent_id_num_avg_data)

 #=========================================================================================================================

    # DIO를 수신한 장치의 수를 구함
    received_dio_id_num_avg_data = []
    for run_id, per_mote_stats in allstats.items():
        received_dio_id_num_sum = 0
        num_mote = 0
        for mote_id, motestats in per_mote_stats.items():
            if 'received_dio_id_list' in motestats:
                unique_received_dio_ids = len(set(motestats['received_dio_id_list']))
                received_dio_id_num_sum += unique_received_dio_ids
                num_mote += 1
        received_dio_id_num_avg_data.append(received_dio_id_num_sum / num_mote)

    avgStates['rpl_received_dio_ids_num'] = calculate_stats(received_dio_id_num_avg_data)
 #=========================================================================================================================
    # 파일 설정에서 실행 시간을 가져옴 (분 단위)
    total_minutes = math.ceil(file_settings['exec_numSlotframesPerRun'] / 60)

    # 결과를 저장할 딕셔너리 초기화
    results = {}
    packet_sums = {}
    minute_counts = {}  # 각 분의 데이터 개수를 저장할 딕셔너리

    # 전체 시간 범위를 생성 (0분부터 total_minutes-1분까지)
    all_minutes = list(range(total_minutes))

    # 각 run_id와 mote_id에 대해 데이터를 수집
    for run_id, per_mote_stats in sorted(allstats.items(), key=lambda x: str(x[0])):  # run_id를 문자열로 변환 후 정렬
        packet_sums[run_id] = {}
        
        for mote_id, motestats in sorted(per_mote_stats.items(), key=lambda x: str(x[0])):  # mote_id를 문자열로 변환 후 정렬
            if 'dio_tx_num' in motestats:
                dio_tx_data = motestats['dio_tx_num']
                
                for minute, hops_data in sorted(dio_tx_data.items()):  # minute을 정렬
                    if minute not in packet_sums[run_id]:
                        packet_sums[run_id][minute] = {}
                    
                    for hops, count in sorted(hops_data.items()):  # hops를 정렬
                        if hops not in packet_sums[run_id][minute]:
                            packet_sums[run_id][minute][hops] = 0
                        
                        packet_sums[run_id][minute][hops] += count

    # 각 run_id에 대한 데이터프레임 생성 및 저장
    for run_id, data in packet_sums.items():
        df_run = pd.DataFrame.from_dict(data, orient='index').fillna(0).sort_index()
        df_run = df_run[sorted(df_run.columns)]  # 열(hops)을 오름차순으로 정렬
        
        # 전체 시간 범위로 인덱스를 맞추고, 비어있는 시간대는 0으로 채움
        df_run = df_run.reindex(all_minutes, fill_value=0)
        
        results[run_id] = df_run

        # 각 분의 데이터를 가진 run_id 수를 계산
        for minute in df_run.index:
            if minute not in minute_counts:
                minute_counts[minute] = 0
            if df_run.loc[minute].sum() > 0:  # 해당 분의 데이터가 있는 경우만 카운트 증가
                minute_counts[minute] += 1

    # 모든 run_id의 평균 계산
    average_packets = {}

    for run_id, df in results.items():
        for minute in df.index:
            if minute not in average_packets:
                average_packets[minute] = {}
            for hops in df.columns:
                if hops not in average_packets[minute]:
                    average_packets[minute][hops] = 0
                average_packets[minute][hops] += df.at[minute, hops]

    # 평균 계산 (각 분에 대해 데이터가 있는 run_id의 개수로 나누기)
    df_average_packets = pd.DataFrame.from_dict(average_packets, orient='index').sort_index()
    df_average_packets = df_average_packets.div(minute_counts.values(), axis=0).fillna(0)
    df_average_packets = df_average_packets.reindex(all_minutes, fill_value=0)  # 동일한 시간 범위로 인덱스를 맞추고 빈 값을 0으로 채움
    df_average_packets = df_average_packets[sorted(df_average_packets.columns)]  # 열(hops)을 오름차순으로 정렬

    # 엑셀 파일로 저장
    with pd.ExcelWriter(subfolder + "\\" + 'dio_tx_summary.xlsx') as writer:
        # 각 run_id 별 시트에 데이터프레임 저장
        for run_id, df in sorted(results.items(), key=lambda x: str(x[0])):  # run_id를 문자열로 변환 후 정렬
            # run_id를 문자열로 변환하여 유효한 시트 이름 생성
            sheet_name = str(run_id) if isinstance(run_id, (int, float)) else run_id
            if not sheet_name.strip():
                sheet_name = 'default_name'
            df.to_excel(writer, sheet_name=sheet_name)
        
        # 모든 run_id의 평균을 마지막 시트에 저장
        df_average_packets.to_excel(writer, sheet_name='Average')

 #========================================================================================================================
    # 데이터 초기화
    desync_num_avg_data = []     # 비동기화 횟수를 구함
    desync_asn_avg_data = []     # 비동기화 시점의 평균
    code_counts_by_code_avg_data = []  # 각 run_id별 코드 개수를 저장
    desync_child_num_data = []
    desync_child_router_num_data = []
    desync_router_num_data = []

    # 모든 run_id에 대해 데이터를 처리
    for run_id, per_mote_stats in allstats.items():
        desync_num_sum = 0
        desync_asn_sum = 0
        num_mote = 0
        num_desync_mote = 0
        desync_child_num = 0
        desync_child_router_num = 0
        desync_router_num = 0
        # 각 코드의 개수를 저장하기 위한 딕셔너리 초기화
        code_count = {'Sync': 0, 'Joined': 0, 'RPL': 0, 'Cell_alloc': 0} 

        # 각 mote에 대한 데이터를 처리
        for mote_id, motestats in per_mote_stats.items():
            if 'desync_asn' in motestats:
                desync_num = len(motestats['desync_asn'])
                desync_num_sum += desync_num
                num_mote += 1

                # 비동기화 장치들의 평균 ASN을 구함
                if desync_num != 0:
                    desync_asn_avg = sum(motestats['desync_asn']) / len(motestats['desync_asn'])
                    desync_asn_sum += desync_asn_avg
                    num_desync_mote += 1

                    # 'desync_code'에서 각 코드별 asn의 개수를 계산
                    desync_codes = motestats.get('desync_code', {})
                    for code in code_count.keys():
                        count = len(desync_codes.get(code, []))
                        code_count[code] += count

                for child_ids in motestats['desync_child_ids']:
                    desync_child_num += len(child_ids)

                for child_router_ids in motestats['desync_child_router_ids']:
                    desync_child_router_num += len(child_router_ids)

                desync_router_num  += motestats['desync_router_num']

        # run_id별 코드 개수를 저장
        code_counts_by_code_avg_data.append(code_count)

        # 비동기화 횟수의 평균을 계산
        if num_mote != 0:
            desync_num_avg_data.append(desync_num_sum / num_mote)

        # 비동기화 장치들의 평균 ASN을 계산
        if num_desync_mote != 0:
            desync_asn_avg_data.append(desync_asn_sum / num_desync_mote)
        
        # 네트워크 전체에서 중계노드 디싱크로 인해 발생하는 자식 노드의 디싱크 횟수를 저장함
        desync_child_num_data.append(desync_child_num)
        desync_child_router_num_data.append(desync_child_router_num)
        desync_router_num_data.append(desync_router_num)

    # 코드별 데이터를 모아 리스트로 변환
    sync_list = [code_counts['Sync'] for code_counts in code_counts_by_code_avg_data]
    joined_list = [code_counts['Joined'] for code_counts in code_counts_by_code_avg_data]
    rpl_list = [code_counts['RPL'] for code_counts in code_counts_by_code_avg_data]
    cell_alloc_list = [code_counts['Cell_alloc'] for code_counts in code_counts_by_code_avg_data]

    # 평균 및 표준편차 계산
    avgStates['desync_num'] = calculate_stats(desync_num_avg_data)
    avgStates['desync_asn'] = calculate_stats(desync_asn_avg_data)
    avgStates['desync_code_sync'] = calculate_stats(sync_list)
    avgStates['desync_code_joined'] = calculate_stats(joined_list)
    avgStates['desync_code_rpl'] = calculate_stats(rpl_list)
    avgStates['desync_code_alloc'] = calculate_stats(cell_alloc_list)
    avgStates['desync_child_num_network'] = calculate_stats(desync_child_num_data)
    avgStates['desync_child_router_num_network'] = calculate_stats(desync_child_router_num_data)
    avgStates['desync_router_num_network'] = calculate_stats(desync_router_num_data)
 #=========================================================================================================================
    # 네트워크에 싱크되어 있던 시간을 측정함
    sync_duration_s_avg_data = []
    for run_id, per_mote_stats in allstats.items():
        sync_duration_s = 0
        num_mote = 0
        for mote_id, motestats in per_mote_stats.items():
            if 'desync_asn' in motestats:
                for i in range(len(motestats['desync_asn'])):
                    sync_duration_s += (motestats['desync_asn'][i] - motestats['sync_asn'][i]) * file_settings['tsch_slotDuration']
                
                if len(motestats['desync_asn']) != len(motestats['sync_asn']):
                    sync_duration_s += (file_settings['exec_numSlotframesPerRun'] * file_settings['tsch_slotframeLength'] - motestats['sync_asn'][-1]) * file_settings['tsch_slotDuration']
                num_mote += 1
        
        sync_duration_s_avg_data.append(sync_duration_s / num_mote)
    avgStates['sync_duration_s'] = calculate_stats(sync_duration_s_avg_data)
 #=========================================================================================================================

    # 네트워크의 APP 패킷 송신 개수를 구함
    app_pkt_num_net_avg_data = []
    for run_id, per_mote_stats in allstats.items():
        app_pkt_num = 0
        for mote_id, motestats in per_mote_stats.items():
            if 'upstream_num_tx' in motestats:
                app_pkt_num += motestats['upstream_num_tx']
        app_pkt_num_net_avg_data.append(app_pkt_num)

    avgStates['app_pkt_num_net'] = calculate_stats(app_pkt_num_net_avg_data)
 #=========================================================================================================================
    # keep alive 패킷 개수를 구함
    kp_num_avg_data = []
    for run_id, per_mote_stats in allstats.items():
        kp_num_sum = 0
        num_mote = 0
        for mote_id, motestats in per_mote_stats.items():
            if 'keep_alive_asn' in motestats:
                kp_num = len(motestats['keep_alive_asn'])
                kp_num_sum += kp_num
                num_mote += 1
        kp_num_avg_data.append(kp_num_sum / num_mote)

    avgStates['keep_alive_asn'] = calculate_stats(kp_num_avg_data)
 #=========================================================================================================================
    kp_success_rate_avg_data = []

    for run_id, per_mote_stats in allstats.items():
        kp_success_rate_sum = 0
        num_mote = 0
        for mote_id, motestats in per_mote_stats.items():
            if 'keep_alive_acked' in motestats:
                if len(motestats['keep_alive_acked']) > 0:
                    kp_success_rate_sum += sum(motestats['keep_alive_acked']) / len(motestats['keep_alive_acked'])
                    num_mote += 1
        
        # 노드별 평균 전송 패킷 수 및 성공률을 구함
        if num_mote > 0:
            kp_success_rate_avg_data.append(kp_success_rate_sum / num_mote)
    # 평균 데이터 계산 및 저장
    avgStates['kp_success_rate_dedicate'] = calculate_stats(kp_success_rate_avg_data)
 #=========================================================================================================================

    auto_tx_kp_num_avg_data = []
    auto_success_rate_kp_avg_data = []
    auto_tx_jrq_num_avg_data = []
    auto_success_rate_jrq_avg_data = []
    auto_tx_6p_num_avg_data = []
    auto_success_rate_6p_avg_data = []
    # 토탈
    auto_tx_num_avg_data = []
    auto_success_rate_avg_data = []

    for run_id, per_mote_stats in allstats.items():
        auto_tx_num_kp_sum = 0
        auto_success_rate_kp_sum = 0
        auto_tx_num_jrq_sum = 0
        auto_success_rate_jrq_sum = 0
        auto_tx_num_6p_sum = 0
        auto_success_rate_6p_sum = 0
        num_mote_kp = 0
        num_mote_jrq = 0
        num_mote_6p = 0
    
        auto_tx_num_sum = 0
        auto_success_rate_sum = 0
        num_mote = 0

        for mote_id, motestats in per_mote_stats.items():
            # KP 처리
            if 'autonomous_tx_acked_kp' in motestats:
                if len(motestats['autonomous_tx_acked_kp']) > 0:
                    auto_tx_num_kp_sum += len(motestats['autonomous_tx_acked_kp'])
                    
                    # True인 값의 비율 계산 (KP)
                    success_count_kp = sum(1 for acked in motestats['autonomous_tx_acked_kp'].values() if acked)
                    auto_success_rate_kp_sum += success_count_kp / len(motestats['autonomous_tx_acked_kp'])
                    num_mote_kp += 1

            # JRQ 처리
            if 'autonomous_tx_acked_jrq' in motestats:
                if len(motestats['autonomous_tx_acked_jrq']) > 0:
                    auto_tx_num_jrq_sum += len(motestats['autonomous_tx_acked_jrq'])
                    
                    # True인 값의 비율 계산 (JRQ)
                    success_count_jrq = sum(1 for acked in motestats['autonomous_tx_acked_jrq'].values() if acked)
                    auto_success_rate_jrq_sum += success_count_jrq / len(motestats['autonomous_tx_acked_jrq'])
                    num_mote_jrq += 1

            # 6P 처리
            if 'autonomous_tx_acked_6p' in motestats:
                if len(motestats['autonomous_tx_acked_6p']) > 0:
                    auto_tx_num_6p_sum += len(motestats['autonomous_tx_acked_6p'])
                    
                    # True인 값의 비율 계산 (6P)
                    success_count_6p = sum(1 for acked in motestats['autonomous_tx_acked_6p'].values() if acked)
                    auto_success_rate_6p_sum += success_count_6p / len(motestats['autonomous_tx_acked_6p'])
                    num_mote_6p += 1


            if 'autonomous_tx_acked' in motestats:
                # autonomous_tx_acked의 길이가 0이 아닌 경우에만 처리
                if len(motestats['autonomous_tx_acked']) > 0:
                    auto_tx_num_sum += len(motestats['autonomous_tx_acked'])
                    # 각 노드의 성공률 계산 (수신된 True의 비율)
                    auto_success_rate_sum += sum(motestats['autonomous_tx_acked']) / len(motestats['autonomous_tx_acked'])
                    num_mote += 1
        
        # 노드별 평균 전송 패킷 수 및 성공률을 구함
        if num_mote > 0:
            auto_tx_num_avg_data.append(auto_tx_num_sum / num_mote)
            auto_success_rate_avg_data.append(auto_success_rate_sum / num_mote)

        # KP의 평균 전송 패킷 수 및 성공률 계산
        if num_mote_kp > 0:
            auto_tx_kp_num_avg_data.append(auto_tx_num_kp_sum / num_mote_kp)
            auto_success_rate_kp_avg_data.append(auto_success_rate_kp_sum / num_mote_kp)

        # JRQ의 평균 전송 패킷 수 및 성공률 계산
        if num_mote_jrq > 0:
            auto_tx_jrq_num_avg_data.append(auto_tx_num_jrq_sum / num_mote_jrq)
            auto_success_rate_jrq_avg_data.append(auto_success_rate_jrq_sum / num_mote_jrq)

        # 6P의 평균 전송 패킷 수 및 성공률 계산
        if num_mote_6p > 0:
            auto_tx_6p_num_avg_data.append(auto_tx_num_6p_sum / num_mote_6p)
            auto_success_rate_6p_avg_data.append(auto_success_rate_6p_sum / num_mote_6p)


    # 평균 데이터 계산 및 저장
    avgStates['auto_tx_kp_num_avg_data'] = calculate_stats(auto_tx_kp_num_avg_data)
    avgStates['auto_success_rate_kp_avg_data'] = calculate_stats(auto_success_rate_kp_avg_data)
    avgStates['auto_tx_jrq_num_avg_data'] = calculate_stats(auto_tx_jrq_num_avg_data)
    avgStates['auto_success_rate_jrq_avg_data'] = calculate_stats(auto_success_rate_jrq_avg_data)
    avgStates['auto_tx_6p_num_avg_data'] = calculate_stats(auto_tx_6p_num_avg_data)
    avgStates['auto_success_rate_sixp_avg_data'] = calculate_stats(auto_success_rate_6p_avg_data)
    avgStates['auto_tx_num_avg_data'] = calculate_stats(auto_tx_num_avg_data)
    avgStates['auto_success_rate_avg_data'] = calculate_stats(auto_success_rate_avg_data)
 #=========================================================================================================================

    asn_group_size = 60000
    all_run_avg_data = {
        'asn_range': [],
        'kp_success_rate': [],
        'jrq_success_rate': [],
        '6p_success_rate': []
    }

    # 모든 run에서 공통 ASN 범위 설정을 위해 ASN 범위를 계산하는 함수
    def get_common_asn_ranges(per_mote_stats, asn_group_size):
        max_asn = max([max(motestats.get('autonomous_tx_acked_kp', {}).keys(), default=0) for motestats in per_mote_stats.values()] +
                    [max(motestats.get('autonomous_tx_acked_jrq', {}).keys(), default=0) for motestats in per_mote_stats.values()] +
                    [max(motestats.get('autonomous_tx_acked_6p', {}).keys(), default=0) for motestats in per_mote_stats.values()])
        total_groups = (max_asn // asn_group_size) + 1
        asn_ranges = [f"{group * asn_group_size}-{(group + 1) * asn_group_size - 1}" for group in range(total_groups)]
        return asn_ranges

    with pd.ExcelWriter("asn_success_rate_all_runs_trgb.xlsx", engine='xlsxwriter') as writer:
        common_asn_ranges = None

        # 각 run에 대한 데이터를 처리
        for run_id, per_mote_stats in allstats.items():
            asn_success_rate_data = {
                'asn_range': [],
                'kp_success_rate': [],
                'jrq_success_rate': [],
                '6p_success_rate': []
            }

            # 공통 ASN 범위 설정 (첫 번째 run 기준)
            if common_asn_ranges is None:
                common_asn_ranges = get_common_asn_ranges(per_mote_stats, asn_group_size)
                all_run_avg_data['asn_range'] = common_asn_ranges

            # 기본값 None으로 모든 ASN 범위를 초기화
            kp_success_data = {asn_range: None for asn_range in common_asn_ranges}
            jrq_success_data = {asn_range: None for asn_range in common_asn_ranges}
            _6p_success_data = {asn_range: None for asn_range in common_asn_ranges}

            # 각 그룹에서 성공률 계산
            for asn_range_str in common_asn_ranges:
                asn_start, asn_end = map(int, asn_range_str.split('-'))

                # 기본값 None으로 설정
                kp_success = None
                jrq_success = None
                _6p_success = None

                kp_count, jrq_count, _6p_count = 0, 0, 0  # 패킷 수

                # KP 처리
                for mote_id, motestats in per_mote_stats.items():
                    if 'autonomous_tx_acked' in motestats:
                        for asn, acked in motestats['autonomous_tx_acked_kp'].items():
                            if asn_start <= asn <= asn_end:
                                kp_count += 1
                                kp_success = kp_success or 0  # None이면 0으로 초기화
                                kp_success += acked  # acked는 True(1) 또는 False(0)

                if kp_count > 0:
                    kp_success_data[asn_range_str] = kp_success / kp_count  # 성공률 계산

                # JRQ 처리
                for mote_id, motestats in per_mote_stats.items():
                    if 'autonomous_tx_acked_jrq' in motestats:
                        for asn, acked in motestats['autonomous_tx_acked_jrq'].items():
                            if asn_start <= asn <= asn_end:
                                jrq_count += 1
                                jrq_success = jrq_success or 0  # None이면 0으로 초기화
                                jrq_success += acked

                if jrq_count > 0:
                    jrq_success_data[asn_range_str] = jrq_success / jrq_count  # 성공률 계산

                # 6P 처리
                for mote_id, motestats in per_mote_stats.items():
                    if 'autonomous_tx_acked_6p' in motestats:
                        for asn, acked in motestats['autonomous_tx_acked_6p'].items():
                            if asn_start <= asn <= asn_end:
                                _6p_count += 1
                                _6p_success = _6p_success or 0  # None이면 0으로 초기화
                                _6p_success += acked

                if _6p_count > 0:
                    _6p_success_data[asn_range_str] = _6p_success / _6p_count  # 성공률 계산

            # 성공률 데이터 저장
            asn_success_rate_data['asn_range'] = common_asn_ranges
            asn_success_rate_data['kp_success_rate'] = [kp_success_data[asn] for asn in common_asn_ranges]
            asn_success_rate_data['jrq_success_rate'] = [jrq_success_data[asn] for asn in common_asn_ranges]
            asn_success_rate_data['6p_success_rate'] = [_6p_success_data[asn] for asn in common_asn_ranges]

            # 각 run_id 데이터를 Excel에 저장
            df = pd.DataFrame(asn_success_rate_data)
            df.to_excel(writer, sheet_name=f'run_{run_id}', index=False)

            # 평균 계산을 위한 데이터 저장
            for i, asn_range in enumerate(common_asn_ranges):
                kp_value = asn_success_rate_data['kp_success_rate'][i]
                jrq_value = asn_success_rate_data['jrq_success_rate'][i]
                _6p_value = asn_success_rate_data['6p_success_rate'][i]

                all_run_avg_data['kp_success_rate'].append(kp_value)
                all_run_avg_data['jrq_success_rate'].append(jrq_value)
                all_run_avg_data['6p_success_rate'].append(_6p_value)

        # 모든 run의 평균 데이터를 처리하여 마지막 시트에 저장
        avg_df_data = {
            'asn_range': all_run_avg_data['asn_range'],
            'kp_success_rate': [],
            'jrq_success_rate': [],
            '6p_success_rate': []
        }

        # 평균 계산 (None 값은 제외하고 평균을 계산)
        for i in range(len(common_asn_ranges)):
            kp_values = [v for v in all_run_avg_data['kp_success_rate'][i::len(common_asn_ranges)] if v is not None]
            jrq_values = [v for v in all_run_avg_data['jrq_success_rate'][i::len(common_asn_ranges)] if v is not None]
            _6p_values = [v for v in all_run_avg_data['6p_success_rate'][i::len(common_asn_ranges)] if v is not None]

            avg_df_data['kp_success_rate'].append(np.mean(kp_values) if kp_values else None)
            avg_df_data['jrq_success_rate'].append(np.mean(jrq_values) if jrq_values else None)
            avg_df_data['6p_success_rate'].append(np.mean(_6p_values) if _6p_values else None)

        # 평균 데이터를 DataFrame으로 변환하여 저장
        avg_df = pd.DataFrame(avg_df_data)
        avg_df.to_excel(writer, sheet_name='average', index=False)

 #=========================================================================================================================
    # DIO의 rank 및 수신 횟수에 대해 조사
    rpl_received_dio_rank_max_data = []
    rpl_received_dio_rank_min_data = []
    rpl_received_dio_rank_mean_data = []

    for run_id, per_mote_stats in allstats.items():
        rank_max = 0
        rank_min = 0
        rank_mean = 0
        num_mote = 0
        for mote_id, motestats in per_mote_stats.items():
            if 'received_dio_rank_list' in motestats:
                rank_list = list(motestats['received_dio_rank_list'].values())
                if len(rank_list) != 0:
                    rank_max += max(rank_list)
                    rank_min += min(rank_list)
                    rank_mean += sum(rank_list)/ len(rank_list)
                    num_mote += 1

        rpl_received_dio_rank_max_data.append(rank_max/num_mote)
        rpl_received_dio_rank_min_data.append(rank_min/num_mote)
        rpl_received_dio_rank_mean_data.append(rank_mean/num_mote)

    avgStates['rpl_received_dio_rank_max'] = calculate_stats(rpl_received_dio_rank_max_data)
    avgStates['rpl_received_dio_rank_min'] = calculate_stats(rpl_received_dio_rank_min_data)
    avgStates['rpl_received_dio_rank_mean'] = calculate_stats(rpl_received_dio_rank_mean_data)

 #=========================================================================================================================
    # # 싱크 이후 DIO의 rank 및 수신 횟수에 대해 조사
    # rpl_received_dio_after_sync_rank_max_data = []
    # rpl_received_dio_after_sync_rank_min_data = []
    # rpl_received_dio_after_sync_rank_mean_data = []
    # rpl_received_dio_after_sync_ids_data = []
    # rpl_received_dio_after_sync_parent_dio_rank_data = []

    # for run_id, per_mote_stats in allstats.items():
    #     rank_max = 0
    #     rank_min = 0
    #     rank_mean = 0
    #     parent_rank = 0
    #     num_of_motes = 0
    #     num_mote = 0
    #     for mote_id, motestats in per_mote_stats.items():
    #         if 'received_dio_rank_list_after_sync' in motestats and mote_id != 0:
    #             rank_list = list(motestats['received_dio_rank_list_after_sync'].values())
    #             if len(rank_list) != 0:
    #                 rank_max += max(rank_list)
    #                 rank_min += min(rank_list)
    #                 rank_mean += sum(rank_list)/ len(rank_list)
    #                 parent_rank += motestats['received_dio_rank_list_after_sync'][motestats['rpl_parent_id']]
    #                 num_of_motes += len(rank_list)
    #                 num_mote += 1

    #     rpl_received_dio_after_sync_rank_max_data.append(rank_max/num_mote)
    #     rpl_received_dio_after_sync_rank_min_data.append(rank_min/num_mote)
    #     rpl_received_dio_after_sync_rank_mean_data.append(rank_mean/num_mote)
    #     rpl_received_dio_after_sync_ids_data.append(num_of_motes/num_mote)
    #     rpl_received_dio_after_sync_parent_dio_rank_data.append(parent_rank/num_mote)

    # avgStates['rpl_received_dio_after_sync_rank_max'] = calculate_stats(rpl_received_dio_after_sync_rank_max_data)
    # avgStates['rpl_received_dio_after_sync_rank_min'] = calculate_stats(rpl_received_dio_after_sync_rank_min_data)
    # avgStates['rpl_received_dio_after_sync_rank_mean'] = calculate_stats(rpl_received_dio_after_sync_rank_mean_data)
    # avgStates['rpl_received_dio_after_sync_ids'] = calculate_stats(rpl_received_dio_after_sync_ids_data)
    # avgStates['rpl_received_dio_after_sync_parent_dio_rank'] = calculate_stats(rpl_received_dio_after_sync_parent_dio_rank_data)

 #=========================================================================================================================
    # 노드 별 마지막 선호 부모 선택 ASN의 분산도를 확인한다
    rpl_parent_selection_asn_distribution = []

    for run_id, per_mote_stats in allstats.items():
        rpl_parent_selection_asns = []
        for mote_id, motestats in per_mote_stats.items():
            if 'rpl_asn' in motestats and motestats['rpl_asn'] is not None:
                rpl_parent_selection_asns.append(motestats['rpl_asn'])

        if len(rpl_parent_selection_asns) > 0:
            standard_deviation = np.std(rpl_parent_selection_asns, ddof=1)  # ddof=1은 표본 표준편차를 의미
        else:
            standard_deviation = 0

        rpl_parent_selection_asn_distribution.append(standard_deviation)
    # 각 run_id의 분산에 대한 통계를 계산
    avgStates['rpl_parent_selection_asn_distribution'] = calculate_stats(rpl_parent_selection_asn_distribution)

 #=========================================================================================================================
    # 노드 별 첫번째 선호 부모 선택 ASN의 분산도를 확인한다
    rpl_parent_selection_first_asn_distribution = []

    for run_id, per_mote_stats in allstats.items():
        rpl_parent_selection_first_asns = []
        for mote_id, motestats in per_mote_stats.items():
            if 'rpl_first_asn' in motestats and motestats['rpl_first_asn'] is not None:
                rpl_parent_selection_first_asns.append(motestats['rpl_first_asn'])

        if len(rpl_parent_selection_first_asns) > 0:
            standard_deviation = np.std(rpl_parent_selection_first_asns, ddof=1)  # ddof=1은 표본 표준편차를 의미
        else:
            standard_deviation = 0

        rpl_parent_selection_first_asn_distribution.append(standard_deviation)
    # 각 run_id의 분산에 대한 통계를 계산
    avgStates['rpl_parent_selection_first_asn_distribution'] = calculate_stats(rpl_parent_selection_first_asn_distribution)

 #=========================================================================================================================
    # 첫번째 싱크타임 조사
    sync_first_asn_data = []

    for run_id, per_mote_stats in allstats.items():
        sync_first_asns = []
        for mote_id, motestats in per_mote_stats.items():
            if 'sync_asn' in motestats and mote_id != 0 and len(motestats['sync_asn']) != 0:
                sync_first_asns.append(motestats['sync_asn'][0])
        # sync_first_asns에 데이터가 있는 경우에만 평균 계산
        if len(sync_first_asns) > 0:
            average_sync_first_asn = sum(sync_first_asns) / len(sync_first_asns)
            sync_first_asn_data.append(average_sync_first_asn)

    # 각 run_id의 첫번째 싱크 타임에 대한 통계를 계산
    avgStates['sync_first_asn'] = calculate_stats(sync_first_asn_data)
    
 #=========================================================================================================================
    # 마지막 홉 정보
    last_hops_avg_data = []

    for run_id, per_mote_stats in allstats.items():
        last_hops = []
        for mote_id, motestats in per_mote_stats.items():
            if 'last_hops' in motestats and mote_id != 0 and motestats['last_hops'] is not None:
                last_hops.append(motestats['last_hops'])

        # sync_first_asns에 데이터가 있는 경우에만 평균 계산
        if len(last_hops) > 0:
            last_hops_avg_data.append(sum(last_hops) / len(last_hops))

    # 각 run_id의 첫번째 싱크 타임에 대한 통계를 계산
    avgStates['last_hops'] = calculate_stats(last_hops_avg_data)
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

    # 시뮬레이션의 평균 싱크 안되어 있던 시간의 에너지 소모량을 계산함
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
   
    for (run_id, per_mote_stats) in allstats.items():
        # 시간에 따른 미니멀셀 혼잡 관련 파라미터 통계
        filled_data_rx_list = [[] for _ in range(1)]
        filled_data_tx_list = [[] for _ in range(1)]
        filled_data_chan_seq_list = [[] for _ in range(1)]

        filled_data_neighbor = []
        filled_data_neighbor_rssi_sum = []
        filled_data_network_nodes_num = []
        filled_data_minimal_cell_utilization = [[] for _ in range(1)]

        for (mote_id, motestats) in per_mote_stats.items():
            if 'num_minimal_cells_rx' in motestats:
                result = {}
                for asn, value in motestats['num_minimal_cells_rx'].items():
                    for i, rx_num in enumerate(value):
                        if i not in result:
                            result[i] = {}
                        result[i][asn] = rx_num

                for i in range(len(result)):
                    filled_data_rx_list[i].append(dict(sorted(result[i].items())))
                    
            if 'minimal_cell_chan_seq' in motestats:
                result = {}
                for asn, value in motestats['minimal_cell_chan_seq'].items():
                    for i, chan in enumerate(value):
                        if i not in result:
                            result[i] = {}
                        result[i][asn] = chan
                for i in range(len(result)):
                    filled_data_chan_seq_list[i].append(dict(sorted(result[i].items())))

            if 'minimal_cell_utilization' in motestats:
                result = {}
                for asn, value in motestats['minimal_cell_utilization'].items():
                    for i, minimal_cell_utilization in enumerate(value):
                        if i not in result:
                            result[i] = {}
                        result[i][asn] = minimal_cell_utilization
                for i in range(len(result)):
                    filled_data_minimal_cell_utilization[i].append(dict(sorted(result[i].items())))

            if 'neighbor_num_per_minimal_cell' in motestats:
                filled_data_neighbor.append(dict(sorted(motestats['neighbor_num_per_minimal_cell'].items())))
            if 'neighbor_rssi_sum' in motestats:
                filled_data_neighbor_rssi_sum.append(dict(sorted(motestats['neighbor_rssi_sum'].items())))
            if 'network_nodes_num' in motestats:
                filled_data_network_nodes_num.append(dict(sorted(motestats['network_nodes_num'].items())))

            if 'num_minimal_cells_tx' in motestats:
                result = {}
                for asn, value in motestats['num_minimal_cells_tx'].items():
                    for i, tx_num in enumerate(value):
                        if i not in result:
                            result[i] = {}
                        result[i][asn] = tx_num

                for i in range(len(result)):
                    filled_data_tx_list[i].append(dict(sorted(result[i].items())))

        # DataFrame 생성 및 행열 바꾸기
        df_rx_list = []
        for data in filled_data_rx_list:
            df_rx_list.append(pd.DataFrame(data).transpose())
        df_tx_list = []
        for data in filled_data_tx_list:
            df_tx_list.append(pd.DataFrame(data).transpose())
        df_neighbor = pd.DataFrame(filled_data_neighbor).transpose()
        df_neighbor_rssi_minimal = pd.DataFrame(filled_data_neighbor_rssi_sum).transpose()
        df_network_nodes_num = pd.DataFrame(filled_data_network_nodes_num).transpose()
        df_minimal_cell_utilization_list = []
        for data in filled_data_minimal_cell_utilization:
            df_minimal_cell_utilization_list.append(pd.DataFrame(data).transpose())
        df_chan_seq_list = []
        for data in filled_data_chan_seq_list:
            df_chan_seq_list.append(pd.DataFrame(data).transpose())
        # 같은 X에 대한 합 계산하여 제일 오른쪽에 추가
        for df_rx in df_rx_list:
            df_rx['rx_sum'] = df_rx.sum(axis=1)
        for df_tx in df_tx_list:
            df_tx['tx_sum'] = df_tx.sum(axis=1)
        df_neighbor['neighbor_sum'] = df_neighbor.sum(axis=1)
        df_neighbor_rssi_minimal['rssi_sum'] = df_neighbor_rssi_minimal.sum(axis=1)
    
        for i, df_minimal_cell_utilization in enumerate(df_minimal_cell_utilization_list):
            df_minimal_cell_utilization['utilization_sum_{}'.format(i)] = df_minimal_cell_utilization.sum(axis=1)

        folder_path = subfolder + '\\time_series_data'
        if not os.path.exists(folder_path):  # 폴더가 존재하지 않으면
            os.makedirs(folder_path)  # 폴더를 생성

        # 현재 시간을 이용하여 파일 이름 생성
        current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        file_name = "{}\mote_{}_{}_{}_({},{},{}).xlsx".format(folder_path, run_id, file_settings['exec_numMotes'], current_time,1,1,d.MSF_MAX_MINIMAL_NUMCELLS)

        # 엑셀 파일로 저장
        with pd.ExcelWriter(file_name) as writer:
            for i, df_rx_ in enumerate(df_rx_list):
                sheet_name = 'rx_{}'.format(i)  # 시트 이름에 숫자를 붙입니다.
                df_rx_.to_excel(writer, sheet_name=sheet_name)
            for i, df_tx_ in enumerate(df_tx_list):
                sheet_name = 'tx_{}'.format(i)  # 시트 이름에 숫자를 붙입니다.
                df_tx_.to_excel(writer, sheet_name=sheet_name)

            df_neighbor.to_excel(writer, sheet_name='neighbor_sum')
            df_neighbor_rssi_minimal.to_excel(writer, sheet_name='rssi_sum_minimal')
            df_network_nodes_num.to_excel(writer, sheet_name='network_nodes_num')
            for i, df_minimal_cell_utilization in enumerate(df_minimal_cell_utilization_list):
                sheet_name = 'utilization_{}'.format(i)  # 시트 이름에 숫자를 붙입니다.
                df_minimal_cell_utilization.to_excel(writer, sheet_name=sheet_name)
            for i, df_chan_seq_ in enumerate(df_chan_seq_list):
                sheet_name = 'chan_seq_{}'.format(i)  # 시트 이름에 숫자를 붙입니다.
                df_chan_seq_.to_excel(writer, sheet_name=sheet_name)

            df_sum = pd.DataFrame()
            for df_rx in df_rx_list:
                if 'rx_sum' not in df_sum:
                    df_sum['rx_sum'] = df_rx['rx_sum']
                else:
                    df_sum['rx_sum'] += df_rx['rx_sum']
            for df_tx in df_tx_list:
                if 'tx_sum' not in df_sum:
                    df_sum['tx_sum'] = df_tx['tx_sum']
                else:
                    df_sum['tx_sum'] += df_tx['tx_sum']

            df_sum['rx/tx'] = df_sum['rx_sum'] / df_sum['tx_sum'] 
            df_sum['neighbor_sum'] = df_neighbor['neighbor_sum']
            df_sum['neighbor_avg'] = df_neighbor['neighbor_sum'] / df_network_nodes_num[0]

            # Initialize utilization_avg
            df_sum['utilization_avg'] = 0
            
            # Calculate utilizations for each i and sum them up
            for i in range(1):
                df_sum['utilization_sum_{}'.format(i)] = df_minimal_cell_utilization_list[i]['utilization_sum_{}'.format(i)] / df_network_nodes_num[0]
                df_sum['utilization_avg'] += df_minimal_cell_utilization_list[i]['utilization_sum_{}'.format(i)] / df_network_nodes_num[0]

            # Calculate the average utilization
            df_sum['rssi_avg'] =  df_neighbor_rssi_minimal['rssi_sum'] / df_neighbor['neighbor_sum']

            df_sum.to_excel(writer, sheet_name='summary')

#=========================================================================================================================
        # 패킷 타입별로 전송된 패킷 개수를 저장할 변수 (네트워크 단위)
        packet_type_tx_count_data = {}

        # 각 run_id에 대해 네트워크 전체의 패킷 타입별 전송 데이터를 합산
        for run_id, per_mote_stats in allstats.items():
            # 각 run_id에 대한 패킷 전송 총합 계산을 위해 초기화
            total_packet_tx_by_run = {}

            for mote_id, motestats in per_mote_stats.items():
                if 'packets_by_type_rx' in motestats:
                    for packet_type, packet_data in motestats['packets_by_type_rx'].items():

                        # 패킷 타입별로 초기화
                        if packet_type not in total_packet_tx_by_run:
                            total_packet_tx_by_run[packet_type] = {
                                'clock_source_rx': 0,
                                'non_clock_source_rx': 0
                            }

                        # 각 모트의 클럭 소스와 비클럭 소스 패킷 개수를 네트워크 차원에서 합산
                        total_packet_tx_by_run[packet_type]['clock_source_rx'] += len(packet_data['clock_source'])
                        total_packet_tx_by_run[packet_type]['non_clock_source_rx'] += len(packet_data['non_clock_source'])

            # 각 run_id에 대한 네트워크 전체 패킷 수 저장
            for packet_type, tx_counts in total_packet_tx_by_run.items():
                # 패킷 타입별로 리스트 초기화
                if packet_type not in packet_type_tx_count_data:
                    packet_type_tx_count_data[packet_type] = {
                        'clock_source_rx_by_run': [],
                        'non_clock_source_rx_by_run': []
                    }

                # 각 run_id의 전체 네트워크에서 전송된 패킷 수를 리스트에 저장
                packet_type_tx_count_data[packet_type]['clock_source_rx_by_run'].append(tx_counts['clock_source_rx'])
                packet_type_tx_count_data[packet_type]['non_clock_source_rx_by_run'].append(tx_counts['non_clock_source_rx'])

        # 각 패킷 타입별로 전체 run_id에 대한 통계를 calculate_stats로 계산
        overall_packet_type_tx_count_stats = {}

        for packet_type, tx_counts in packet_type_tx_count_data.items():
            # 각 run_id의 클럭 소스 패킷 개수에 대한 통계 계산
            if len(tx_counts['clock_source_rx_by_run']) > 0:
                clock_source_stats = calculate_stats(tx_counts['clock_source_rx_by_run'])
            else:
                clock_source_stats = {'mean': None, 'std_dev': None, 'margin_of_error': None}

            # 각 run_id의 비클럭 소스 패킷 개수에 대한 통계 계산
            if len(tx_counts['non_clock_source_rx_by_run']) > 0:
                non_clock_source_stats = calculate_stats(tx_counts['non_clock_source_rx_by_run'])
            else:
                non_clock_source_stats = {'mean': None, 'std_dev': None, 'margin_of_error': None}

            # 결과를 저장
            overall_packet_type_tx_count_stats[packet_type] = {
                'clock_source_stats': clock_source_stats,
                'non_clock_source_stats': non_clock_source_stats
            }

        # 최종 결과를 avgStates에 저장
        avgStates['packets_by_type_rx_count_network'] = overall_packet_type_tx_count_stats
    #=========================================================================================================================
    # 모든 패킷 타입에 대해 클럭 소스로부터 수신한 ASN 리스트를 만들고, 인터벌을 계산하는 코드
    clock_packet_rx_asn_list = {}
    eb_packet_rx_asn_list = {}  # EB 패킷에 대한 ASN 리스트 저장
    dio_packet_rx_asn_list = {}  # DIO 패킷에 대한 ASN 리스트 저장

    # 각 run_id에 대해 모트별로 수신된 패킷의 ASN 리스트를 수집
    for run_id, per_mote_stats in allstats.items():
        # 각 모트별로 초기화
        clock_packet_rx_asn_list[run_id] = {}
        eb_packet_rx_asn_list[run_id] = {}
        dio_packet_rx_asn_list[run_id] = {}

        for mote_id, motestats in per_mote_stats.items():
            if 'packets_by_type_rx' in motestats:
                # 모든 패킷 타입에 대해 반복
                for packet_type, packet_data in motestats['packets_by_type_rx'].items():
                    # 클럭 소스에서 수신한 패킷 필터링 (전체 ASN 수집)
                    if 'clock_source' in packet_data and len(packet_data['clock_source']) > 0:
                        if mote_id not in clock_packet_rx_asn_list[run_id]:
                            clock_packet_rx_asn_list[run_id][mote_id] = []
                        clock_packet_rx_asn_list[run_id][mote_id].extend(packet_data['clock_source'])
                    # EB 패킷에 대해 ASN 수집
                    if packet_type == d.PKT_TYPE_EB and len(packet_data['clock_source']) > 0:
                        if mote_id not in eb_packet_rx_asn_list[run_id]:
                            eb_packet_rx_asn_list[run_id][mote_id] = []
                        eb_packet_rx_asn_list[run_id][mote_id].extend(packet_data['clock_source'])
                           
                    # DIO 패킷에 대해 ASN 수집
                    if packet_type == d.PKT_TYPE_DIO and len(packet_data['clock_source']) > 0:
                        if mote_id not in dio_packet_rx_asn_list[run_id]:
                            dio_packet_rx_asn_list[run_id][mote_id] = []
                        dio_packet_rx_asn_list[run_id][mote_id].extend(packet_data['clock_source'])
            

    # 인터벌 계산 및 run_id 별로 저장
    clock_packet_rx_intervals = {}
    eb_packet_rx_intervals = {}
    dio_packet_rx_intervals = {}

    for run_id in clock_packet_rx_asn_list:
        clock_packet_rx_intervals[run_id] = {}
        eb_packet_rx_intervals[run_id] = {}
        dio_packet_rx_intervals[run_id] = {}

        for mote_id, asn_list in clock_packet_rx_asn_list[run_id].items():
            if len(asn_list) > 1:
                asn_list =   sorted(asn_list)
                intervals = [asn_list[i + 1] - asn_list[i] for i in range(len(asn_list) - 1)]
                clock_packet_rx_intervals[run_id][mote_id] = intervals

        for mote_id, eb_asn_list in eb_packet_rx_asn_list[run_id].items():
            if len(eb_asn_list) > 1:
                eb_asn_list = sorted(eb_asn_list)
                eb_intervals = [eb_asn_list[i + 1] - eb_asn_list[i] for i in range(len(eb_asn_list) - 1)]
                eb_packet_rx_intervals[run_id][mote_id] = eb_intervals

        for mote_id, dio_asn_list in dio_packet_rx_asn_list[run_id].items():
            if len(dio_asn_list) > 1:
                dio_asn_list = sorted(dio_asn_list)
                dio_intervals = [dio_asn_list[i + 1] - dio_asn_list[i] for i in range(len(dio_asn_list) - 1)]
                dio_packet_rx_intervals[run_id][mote_id] = dio_intervals

    # 모트별 평균을 구한 후, run_id 별 평균을 구하고 그 결과를 다시 전체 run_id 에 대해 평균 계산
    clock_avg_intervals_per_run = {}
    eb_avg_intervals_per_run = {}
    dio_avg_intervals_per_run = {}

    for run_id in clock_packet_rx_intervals:
        clock_avg_intervals_per_run[run_id] = []
        eb_avg_intervals_per_run[run_id] = []
        dio_avg_intervals_per_run[run_id] = []

        # 모트별로 평균 주기 계산
        for mote_id, intervals in clock_packet_rx_intervals[run_id].items():
            if len(intervals) > 0:
                clock_avg_intervals_per_run[run_id].append(sum(intervals) / len(intervals))

        for mote_id, eb_intervals in eb_packet_rx_intervals[run_id].items():
            if len(eb_intervals) > 0:
                eb_avg_intervals_per_run[run_id].append(sum(eb_intervals) / len(eb_intervals))

        for mote_id, dio_intervals in dio_packet_rx_intervals[run_id].items():
            if len(dio_intervals) > 0:
                dio_avg_intervals_per_run[run_id].append(sum(dio_intervals) / len(dio_intervals))

    # 각 run_id 의 평균 주기를 다시 전체 run_id에 대해 통계 계산
    final_clock_avg_intervals = [sum(values) / len(values) for values in clock_avg_intervals_per_run.values() if len(values) > 0]
    final_eb_avg_intervals = [sum(values) / len(values) for values in eb_avg_intervals_per_run.values() if len(values) > 0]
    final_dio_avg_intervals = [sum(values) / len(values) for values in dio_avg_intervals_per_run.values() if len(values) > 0]

    # calculate_stats를 사용해 최종 결과 계산
    if final_clock_avg_intervals:
        avgStates['clock_source_rx_avg_interval'] = calculate_stats(final_clock_avg_intervals)

    if final_eb_avg_intervals:
        avgStates['clock_source_eb_rx_avg_interval'] = calculate_stats(final_eb_avg_intervals)

    if final_dio_avg_intervals:
        avgStates['clock_source_dio_rx_avg_interval'] = calculate_stats(final_dio_avg_intervals)

#=========================================================================================================================

    # 패킷 타입별로 통계 데이터를 저장할 변수 (전체 네트워크 단위로)
    packet_type_tx_avg_data = {}

    # 각 run_id에 대해 네트워크 전체의 패킷 타입별 전송 데이터를 합산
    for run_id, per_mote_stats in allstats.items():
        # 각 run_id에 대한 패킷 전송 총합 계산을 위해 초기화
        total_packet_tx_by_run = {}

        for mote_id, motestats in per_mote_stats.items():
            if 'packets_by_type_tx' in motestats:
                for packet_type, packet_data in motestats['packets_by_type_tx'].items():

                    # 패킷 타입별로 초기화 (전체 run_id를 합산)
                    if packet_type not in total_packet_tx_by_run:
                        total_packet_tx_by_run[packet_type] = 0

                    # 각 모트의 패킷 수를 네트워크 차원에서 합산
                    total_packet_tx_by_run[packet_type] += len(packet_data)

        # 각 run_id에 대한 전체 네트워크 패킷 수 저장
        for packet_type, total_packets in total_packet_tx_by_run.items():
            # 패킷 타입별로 리스트 초기화
            if packet_type not in packet_type_tx_avg_data:
                packet_type_tx_avg_data[packet_type] = {
                    'packet_tx_num_by_run': []
                }

            # run_id별 전체 네트워크에서 전송된 패킷 수를 리스트에 저장
            packet_type_tx_avg_data[packet_type]['packet_tx_num_by_run'].append(total_packets)

    # 각 패킷 타입별로 전체 네트워크에 대한 통계 계산
    overall_packet_type_tx_avg = {}

    for packet_type, data in packet_type_tx_avg_data.items():
        # 각 패킷 타입별로 run_id 단위로 전송된 패킷 수에 대한 통계 계산
        if len(data['packet_tx_num_by_run']) > 0:
            stats = calculate_stats(data['packet_tx_num_by_run'])  # 평균, 표준 편차, 신뢰 구간 계산
        else:
            stats = {'mean': None, 'std_dev': None, 'margin_of_error': None}

        # 전체 패킷 타입에 대한 결과 저장
        overall_packet_type_tx_avg[packet_type] = stats

    # 최종 결과를 avgStates에 저장
    avgStates['packets_by_type_tx_network'] = overall_packet_type_tx_avg
#=========================================================================================================================
    # 중복 체크 및 병합 함수 (완전 겹치거나 부분 겹치는 경우 처리)
    def merge_and_remove_overlaps(periods):
        # 우선 시작점 순으로 정렬
        periods.sort(key=lambda x: x['start'])

        merged = []
        for current in periods:
            if not merged:
                merged.append(current)
            else:
                last = merged[-1]
                # 두 기간이 겹치는 경우: 부분적으로든 완전히 겹치든
                if last['end'] >= current['start']:
                    # 겹치는 경우에는 시작점은 last['start'], 끝점은 더 큰 값으로 병합
                    last['end'] = max(last['end'], current['end'])
                else:
                    merged.append(current)
        return merged
    
    # 세 가지 리스트를 병합하고 중복을 제거하는 함수
    def merge_all_periods(mote_id):
        # 세 가지 리스트에서 구간을 가져오기
        periods = []
        
        # rpl_only_between_sync_and_addcell 리스트에서 기간 가져오기
        if mote_id in rpl_only_between_sync_and_addcell:
            periods.extend(rpl_only_between_sync_and_addcell[mote_id])

        # rpl_followed_by_addcell_or_desync 리스트에서 기간 가져오기
        if mote_id in rpl_followed_by_addcell_or_desync:
            periods.extend(rpl_followed_by_addcell_or_desync[mote_id])

        # sync_followed_by_desync 리스트에서 기간 가져오기
        if mote_id in sync_followed_by_desync:
            periods.extend(sync_followed_by_desync[mote_id])

        # 중복된 기간을 병합
        merged_periods = merge_and_remove_overlaps(periods)
        
        return merged_periods

    non_nego_periods_by_mote_by_run = {}
    sorted_sync_desync_events_by_run = {}
    for run_id, per_mote_stats in allstats.items():     
        sorted_events_by_mote = {}  # 모트별 정렬된 이벤트 저장
        sorted_sync_desync_events_by_mote = {}  # 싱크 디싱크 이벤트만 저장
        rpl_only_between_sync_and_addcell = {}  # sync와 add셀 사이에 rpl만 있는 케이스 저장
        rpl_followed_by_addcell_or_desync = {}  # rpl 뒤에 add_cell 또는 desync가 오는 케이스 저장
        sync_followed_by_desync = {}  # sync 뒤에  desync가 오는 케이스 저장

        for mote_id, motestats in per_mote_stats.items():

            # 싱크, 디싱크, 부모 선정, 셀 할당 ASN 리스트들 (여러 번 발생 가능)
            sync_asn_list = motestats.get('sync_asn', [])
            desync_asn_list = motestats.get('desync_asn', [])
            rpl_asn_list = motestats.get('rpl_asn_total', [])
            add_cell_asn_list = motestats.get('add_cell_asn', [])

            # 이벤트 리스트 생성
            events = []
            events += [{'type': 'sync', 'asn': asn} for asn in sync_asn_list]
            events += [{'type': 'desync', 'asn': asn} for asn in desync_asn_list]
            events += [{'type': 'rpl', 'asn': asn} for asn in rpl_asn_list]
            events += [{'type': 'add_cell', 'asn': asn} for asn in add_cell_asn_list]

            sync_desync_events = []
            sync_desync_events += [{'type': 'sync', 'asn': asn} for asn in sync_asn_list]
            sync_desync_events += [{'type': 'desync', 'asn': asn} for asn in desync_asn_list]

            # ASN 기준으로 정렬
            events.sort(key=lambda x: x['asn'])
            sync_desync_events.sort(key=lambda x: x['asn'])

            # 정렬된 이벤트 저장
            sorted_events_by_mote[mote_id] = events
            sorted_sync_desync_events_by_mote[mote_id] = sync_desync_events
            
            # 1. rpl만 sync와 add셀 사이에 있는 경우 찾기
            sync_index = None
            for i, event in enumerate(events):
                if event['type'] == 'sync':
                    sync_index = i  # sync 이벤트 발생 지점 기록
                elif sync_index is not None and event['type'] == 'add_cell':
                    # sync 이후 add셀 이벤트 발생 시점에 rpl만 있는지 확인
                    if all(e['type'] == 'rpl' for e in events[sync_index + 1:i]):
                        # rpl_only_between_sync_and_addcell 리스트에 저장
                        rpl_only_between_sync_and_addcell.setdefault(mote_id, []).append({
                            'start': events[sync_index]['asn'],
                            'end': event['asn']
                        })
                    sync_index = None  # sync와 add셀 사이 확인 후 초기화
            # 2. rpl 뒤에 바로 add_cell 또는 desync가 오는 경우 찾기
            for i in range(len(events) - 1):
                current_event = events[i]
                next_event = events[i + 1]
                
                # rpl 이벤트가 있고, 다음에 add_cell 또는 desync가 오는 경우
                if current_event['type'] == 'rpl' and next_event['type'] in ['add_cell', 'desync']:
                    # rpl_followed_by_addcell_or_desync 리스트에 저장
                    rpl_followed_by_addcell_or_desync.setdefault(mote_id, []).append({
                        'start': current_event['asn'],
                        'end': next_event['asn']
                    })

            # 3. sync 뒤에 바로 desync
            for i in range(len(events) - 1):
                current_event = events[i]
                next_event = events[i + 1]
                
                # sync 이벤트가 있고, 다음에  desync가 오는 경우
                if current_event['type'] == 'sync' and next_event['type'] in ['desync']:
                    # sync_followed_by_desync 리스트에 저장
                    sync_followed_by_desync.setdefault(mote_id, []).append({
                        'start': current_event['asn'],
                        'end': next_event['asn']
                    })

        non_nego_periods_by_mote = {}

        for mote_id in rpl_only_between_sync_and_addcell.keys() | rpl_followed_by_addcell_or_desync.keys() | sync_followed_by_desync.keys():
            # 세 리스트를 병합하고 중복을 제거
            merged_periods = merge_all_periods(mote_id)
            non_nego_periods_by_mote[mote_id] = merged_periods


        non_nego_periods_by_mote_by_run[run_id] = non_nego_periods_by_mote
        sorted_sync_desync_events_by_run[run_id] = sorted_sync_desync_events_by_mote

    # 중복 체크 및 구간 제거 함수
    def subtract_periods(sync_periods, non_nego_periods):
        result = []
        for sync_period in sync_periods:
            start = sync_period['start']
            end = sync_period['end']
            for non_nego_period in non_nego_periods:
                if non_nego_period['start'] <= end and non_nego_period['end'] >= start:  # 구간이 겹치는 경우
                    if non_nego_period['start'] > start:
                        result.append({'start': start, 'end': non_nego_period['start'] - 1})
                    start = max(non_nego_period['end'] + 1, start)
            if start <= end:  # 남은 부분이 있을 경우
                result.append({'start': start, 'end': end})
        return result

    # 각 run_id에 대해 협상 셀 구간 계산
    nego_periods_by_mote_by_run = {}

    for run_id, non_nego_periods_by_mote in non_nego_periods_by_mote_by_run.items():
        nego_periods_by_mote = {}
        # 시뮬레이션 종료 ASN 계산
        sim_end_asn = file_settings['exec_numSlotframesPerRun'] * file_settings['tsch_slotframeLength']
        
        for mote_id, sync_desync_events in sorted_sync_desync_events_by_run[run_id].items():
            # 싱크-디싱크 구간 만들기
            sync_periods = []
            sync_start = None
            for event in sync_desync_events:
                if event['type'] == 'sync':
                    sync_start = event['asn']  # 싱크 시작점 기록
                elif event['type'] == 'desync' and sync_start is not None:
                    sync_periods.append({'start': sync_start, 'end': event['asn']})  # 싱크-디싱크 구간 저장
                    sync_start = None

            # 마지막 싱크 후 디싱크가 없으면 시뮬레이션 종료까지 싱크 상태로 유지
            if sync_start is not None:
                sync_periods.append({'start': sync_start, 'end': sim_end_asn})

            # non_nego 구간 가져오기
            non_nego_periods = non_nego_periods_by_mote.get(mote_id, [])

            # 싱크-디싱크 구간에서 non_nego 구간을 제거하여 협상 구간 계산
            nego_periods = subtract_periods(sync_periods, non_nego_periods)
            nego_periods_by_mote[mote_id] = nego_periods

        # 각 run_id에 대해 협상 구간 저장
        nego_periods_by_mote_by_run[run_id] = nego_periods_by_mote

#========================================전처리===============================================

    # 클럭 소스로부터 weak_period 동안 수신한 패킷 수의 평균을 계산하기 위한 데이터 저장
    packets_in_weak_period_data_by_type = {}
    total_weak_period_data = []

    # 각 run_id에 대해 네트워크 전체의 패킷 타입별 전송 데이터를 합산
    for run_id, per_mote_stats in allstats.items():
        # 각 run_id에 대한 패킷 전송 총합 계산을 위해 초기화
        total_packet_tx_by_run = {}
        total_weak_period = 0
        non_nego_periods_by_mote = non_nego_periods_by_mote_by_run[run_id]
        # 각 패킷 타입에 대해 weak_period 동안 받은 패킷 수를 저장하기 위한 구조 초기화
        for mote_id, motestats in per_mote_stats.items():
            if 'packets_by_type_rx' in motestats:

                weak_period = non_nego_periods_by_mote.get(mote_id, [])

                # 약한 기간(weak period)의 총 ASN 개수 계산
                total_weak_period += sum(period['end'] - period['start'] + 1 for period in weak_period)

                for packet_type, packet_data in motestats['packets_by_type_rx'].items():
                    # 각 패킷 타입별로 평균 계산을 위한 초기화
                    if packet_type not in total_packet_tx_by_run:
                        total_packet_tx_by_run[packet_type] = 0

                    if packet_type not in packets_in_weak_period_data_by_type:
                        packets_in_weak_period_data_by_type[packet_type] = []

                    # 각 모트의 클럭 소스에서 받은 패킷의 ASN을 확인하여 기간 내에 있는지 검사
                    for asn in packet_data['clock_source']:
                        for period in weak_period:
                            if period['start'] <= asn <= period['end']:  # ASN이 weak period에 있을 때
                                total_packet_tx_by_run[packet_type] += 1
                                break  # 기간 내에 속한 패킷이 확인되면 다음 ASN 확인

        # 패킷 타입별로 받은 패킷 수를 저장
        for packet_type, count in total_packet_tx_by_run.items():
            packets_in_weak_period_data_by_type[packet_type].append(count)

        # 전체 약한 기간에 대한 데이터 저장 (전체 weak_period 동안의 ASN 개수)
        total_weak_period_data.append(total_weak_period)

    # 패킷 타입별로 weak period 동안 수신된 패킷의 평균 계산
    avgStates['weak_period_network'] = calculate_stats(total_weak_period_data)

    # 각 패킷 타입별 통계 계산 및 저장
    for packet_type, packet_counts in packets_in_weak_period_data_by_type.items():
        avgStates[f'packets_in_weak_period_network_{packet_type}'] = calculate_stats(packet_counts)

 #========================================================================================================================
    # 데이터 초기화
    desync_nego_child_num_data = []  # 부모가 디싱크될 때 자식 노드가 협상 셀이 있는 기간에 있는 경우
    desync_non_nego_child_num_data = []  # 부모가 디싱크될 때 자식 노드가 협상 셀이 없는 기간에 있는 경우
    desync_nego_child_router_num_data = []  # 부모가 디싱크될 때 자식 라우터 노드가 협상 셀이 있는 기간에 있는 경우
    desync_non_nego_child_router_num_data = []  # 부모가 디싱크될 때 자식 라우터 노드가 협상 셀이 없는 기간에 있는 경우

    # 모든 run_id에 대해 데이터를 처리
    for run_id, per_mote_stats in allstats.items():
        desync_nego_child_num = 0
        desync_non_nego_child_num = 0
        desync_nego_child_router_num = 0
        desync_non_nego_child_router_num = 0

        # 해당 run_id의 협상 셀이 있는 기간과 없는 기간 가져오기
        nego_periods_by_mote = nego_periods_by_mote_by_run.get(run_id, {})
        non_nego_periods_by_mote = non_nego_periods_by_mote_by_run.get(run_id, {})

        # 각 mote에 대한 데이터를 처리
        for mote_id, motestats in per_mote_stats.items():

            if 'desync_asn' in motestats:
                # 부모 모트의 디싱크 ASN
                desync_asn_list = motestats['desync_asn']

                # 자식 노드 ID 리스트 가져오기 (개별 자식 노드 ID로 처리)
                child_ids_per_asn = motestats.get('desync_child_ids', [])
                child_router_ids_per_asn = motestats.get('desync_child_router_ids', [])
                
                # 부모 모트가 디싱크될 때 자식들의 상태를 확인
                for index, asn in enumerate(desync_asn_list):
                    # 자식 노드 리스트가 있는지 확인하고, 해당 인덱스의 자식 노드를 가져옴
                    child_ids = child_ids_per_asn[index] if index < len(child_ids_per_asn) else []
                    child_router_ids = child_router_ids_per_asn[index] if index < len(child_router_ids_per_asn) else []

                    # 디싱크 후 1750 ASN 이내의 범위 확인
                    asn_end = asn + 1750

                    # 자식 노드가 있는 경우 처리
                    if child_ids:
                        for child_id in child_ids:
                            # 자식 노드의 디싱크 ASN 리스트 가져오기
                            child_desync_asns = per_mote_stats.get(child_id, {}).get('desync_asn', [])

                            # 자식 노드가 디싱크된 ASN이 1750 ASN 내에 있는지 확인
                            for child_asn in child_desync_asns:
                                if asn <= child_asn <= asn_end:
                                    # 자식 노드의 협상 셀 기간과 상태를 확인
                                    child_nego_periods = nego_periods_by_mote.get(child_id, [])
                                    child_non_nego_periods = non_nego_periods_by_mote.get(child_id, [])

                                    # 자식 노드가 협상 셀이 있는 기간에 있는지 확인
                                    if any(period['start'] <= child_asn <= period['end'] for period in child_nego_periods):
                                        desync_nego_child_num += 1
                                    # 자식 노드가 협상 셀이 없는 기간에 있는지 확인
                                    elif any(period['start'] <= child_asn <= period['end'] for period in child_non_nego_periods):
                                        desync_non_nego_child_num += 1

                    # 자식 라우터 노드가 있는 경우 처리
                    if child_router_ids:
                        for child_router_id in child_router_ids:
                            # 자식 라우터 노드의 디싱크 ASN 리스트 가져오기
                            child_router_desync_asns = per_mote_stats.get(child_router_id, {}).get('desync_asn', [])

                            # 자식 라우터 노드가 디싱크된 ASN이 1750 ASN 내에 있는지 확인
                            for child_router_asn in child_router_desync_asns:
                                if asn <= child_router_asn <= asn_end:
                                    # 자식 라우터 노드의 협상 셀 기간과 상태를 확인
                                    child_router_nego_periods = nego_periods_by_mote.get(child_router_id, [])
                                    child_router_non_nego_periods = non_nego_periods_by_mote.get(child_router_id, [])

                                    # 자식 라우터 노드가 협상 셀이 있는 기간에 있는지 확인
                                    if any(period['start'] <= child_router_asn <= period['end'] for period in child_router_nego_periods):
                                        desync_nego_child_router_num += 1
                                    # 자식 라우터 노드가 협상 셀이 없는 기간에 있는지 확인
                                    elif any(period['start'] <= child_router_asn <= period['end'] for period in child_router_non_nego_periods):
                                        desync_non_nego_child_router_num += 1


        # 각 run_id에 대한 결과 저장
        desync_nego_child_num_data.append(desync_nego_child_num)
        desync_non_nego_child_num_data.append(desync_non_nego_child_num)
        desync_nego_child_router_num_data.append(desync_nego_child_router_num)
        desync_non_nego_child_router_num_data.append(desync_non_nego_child_router_num)

    # 평균 및 표준편차 계산
    avgStates['desync_nego_child_num_network'] = calculate_stats(desync_nego_child_num_data)
    avgStates['desync_non_nego_child_num_network'] = calculate_stats(desync_non_nego_child_num_data)
    avgStates['desync_nego_child_router_num_network'] = calculate_stats(desync_nego_child_router_num_data)
    avgStates['desync_non_nego_child_router_num_network'] = calculate_stats(desync_non_nego_child_router_num_data)


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
        avg, kpis = kpis_all(infile, subfolder)

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
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
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
