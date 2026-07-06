"""Change Queue core - fila de mudanças pendentes de sincronismo.

Persiste em .pipe/changeQueue.json um array de ChangeItem, cada um descrevendo
uma issue que precisa de algum ato de sincronismo (criar, alterar ou deletar,
em qualquer direção entre local e board).

O acesso ao arquivo é isolado: somente add(), addAll(), getNext() e remove()
leem ou escrevem .pipe/changeQueue.json.

Modelo at-least-once (não perde trabalho):
  - getNext() apenas espia o item mais antigo (não remove).
  - remove(uuid) confirma o processamento e remove o item.
O consumidor faz: item = getNext() -> processa -> remove(item.uuid).
Se o processo falhar antes do remove(), o mesmo item volta no próximo getNext().
"""

import json
import uuid as uuidlib
from dataclasses import asdict, fields as dataclass_fields
from pathlib import Path

from src.core.board import ChangeItem

PIPE_DIR = Path(".pipe")
QUEUE_FILE = PIPE_DIR / "changeQueue.json"


class ChangeQueue:
    """Fila persistente de mudanças de sincronismo.

    Únicos pontos de acesso ao arquivo: add(), addAll(), getNext(), remove().
    """

    # ── Acesso ao arquivo (privado) ──────────────────────────────────────────

    def _read(self) -> list[ChangeItem]:
        if not QUEUE_FILE.exists():
            return []
        raw = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        fields = {f.name for f in dataclass_fields(ChangeItem)}
        # Ignora campos desconhecidos (ex: arquivos de versões anteriores)
        return [ChangeItem(**{k: v for k, v in item.items() if k in fields}) for item in raw]

    def _write(self, items: list[ChangeItem]) -> None:
        PIPE_DIR.mkdir(parents=True, exist_ok=True)
        data = [asdict(item) for item in items]
        QUEUE_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── API pública ──────────────────────────────────────────────────────────

    def add(self, item: ChangeItem) -> bool:
        """Adiciona um item à fila, atribuindo um uuid.

        Ignora se já houver item equivalente. Retorna True se adicionou.

        Upgrade de fullsync: se já existe um item equivalente que NÃO é
        fullsync e o novo é fullsync, promove o existente para fullsync=True
        (o full é superset do parcial) e retorna False (não duplica).
        """
        items = self._read()
        for existing in items:
            if existing.same_target(item):
                if item.fullsync and not existing.fullsync:
                    existing.fullsync = True
                    self._write(items)
                return False
        item.uuid = str(uuidlib.uuid4())
        items.append(item)
        self._write(items)
        return True

    def addAll(self, new_items: list[ChangeItem]) -> int:
        """Adiciona vários itens (deduplicando entre si e com a fila).

        Cada item adicionado recebe um uuid. Retorna a quantidade adicionada.
        Aplica upgrade de fullsync sobre itens equivalentes já presentes.
        """
        items = self._read()
        added = 0
        dirty = False
        for item in new_items:
            existing = next(
                (e for e in items if e.same_target(item)), None
            )
            if existing is not None:
                if item.fullsync and not existing.fullsync:
                    existing.fullsync = True
                    dirty = True
                continue
            item.uuid = str(uuidlib.uuid4())
            items.append(item)
            added += 1
            dirty = True
        if dirty:
            self._write(items)
        return added

    def size(self) -> int:
        """Retorna a quantidade de itens na fila."""
        return len(self._read())

    def getNext(self) -> ChangeItem | None:
        """Espia o item mais antigo da fila sem removê-lo (FIFO).

        Chamadas repetidas retornam o mesmo item enquanto ele não for removido
        via remove(uuid). Retorna None se a fila está vazia.
        """
        items = self._read()
        return items[0] if items else None

    def remove(self, uuid: str) -> bool:
        """Remove da fila o item com o uuid informado (confirma processamento).

        Retorna True se removeu, False se não encontrou.
        """
        items = self._read()
        remaining = [i for i in items if i.uuid != uuid]
        if len(remaining) == len(items):
            return False
        self._write(remaining)
        return True
