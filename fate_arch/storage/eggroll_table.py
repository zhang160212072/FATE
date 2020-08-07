#
#  Copyright 2019 The FATE Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import typing
import uuid
from typing import Iterable

from arch.api.utils.conf_utils import get_base_config
from eggroll.core.session import session_init
from eggroll.roll_pair.roll_pair import RollPairContext
from fate_arch.abc import TableABC
from fate_arch.common import WorkMode
from fate_arch.common.profile import log_elapsed
from fate_arch.storage.address import EggRollAddress
from fate_arch.storage.constant import StorageEngine


# noinspection SpellCheckingInspection,PyProtectedMember,PyPep8Naming
class EggRollTable(TableABC):
    def __init__(self,
                 job_id: str = uuid.uuid1().hex,
                 mode: typing.Union[int, WorkMode] = get_base_config('work_mode', 0),
                 persistent_engine: str = StorageEngine.LMDB,
                 partitions: int = 1,
                 namespace: str = None,
                 name: str = None,
                 address=None,
                 **kwargs):
        self._name = name
        self._namespace = namespace
        self._mode = mode
        if not address:
            address = EggRollAddress(name=name, namespace=namespace, storage_type=persistent_engine)
        self._address = address
        self._storage_engine = persistent_engine
        self._session_id = job_id
        self._partitions = partitions
        self.session = _get_session(session_id=self._session_id, work_mode=mode)
        self._table = self.session.table(namespace=address.namespace, name=address.name, partition=partitions,
                                         **kwargs)

    def get_partitions(self):
        return self._table.get_partitions()

    def get_name(self):
        return self._name

    def get_namespace(self):
        return self._namespace

    def get_storage_engine(self):
        return self._storage_engine

    def get_address(self):
        return self._address

    def put_all(self, kv_list: Iterable, **kwargs):
        return self._table.put_all(kv_list)

    @log_elapsed
    def collect(self, **kwargs) -> list:
        return self._table.get_all(**kwargs)

    def destroy(self):
        super().destroy()
        return self._table.destroy()

    @log_elapsed
    def save_as(self, name=None, namespace=None, partition=None, schema=None, **kwargs):
        super().save_as(name, namespace, schema=schema, partition=partition)

        options = kwargs.get("options", {})
        store_type = options.get("store_type", StorageEngine.LMDB)
        options["store_type"] = store_type

        if partition is None:
            partition = self._partitions
        self._table.save_as(name=name, namespace=namespace, partition=partition, options=options).disable_gc()

    def close(self):
        self.session.stop()

    @log_elapsed
    def count(self, **kwargs):
        return self._table.count()


def _get_session(session_id='', work_mode: int = 0, options: dict = None):
    if not session_id:
        session_id = str(uuid.uuid1())
    return _Session(session_id=session_id, work_mode=work_mode, options=options)


class _Session(object):
    def __init__(self, session_id, work_mode, options: dict = None):
        if options is None:
            options = {}
        if work_mode == WorkMode.STANDALONE:
            options['eggroll.session.deploy.mode'] = "standalone"
        elif work_mode == WorkMode.CLUSTER:
            options['eggroll.session.deploy.mode'] = "cluster"
        self._rp_session = session_init(session_id=session_id, options=options)
        self._rpc = RollPairContext(session=self._rp_session)
        self._session_id = self._rp_session.get_session_id()

    def table(self,
              name,
              namespace,
              partition,
              **kwargs):
        options = kwargs.get("option", {})
        options.update(dict(total_partitions=partition))
        _table = self._rpc.load(namespace=namespace, name=name, options=options)
        return _table

    def _get_session_id(self):
        return self._session_id

    @log_elapsed
    def cleanup(self, name, namespace):
        self._rpc.cleanup(name=name, namespace=namespace)

    @log_elapsed
    def stop(self):
        return self._rp_session.stop()

    @log_elapsed
    def kill(self):
        return self._rp_session.kill()