// Sistema de notificacao (pub/sub) — espelha game/events.py.
// Nao ha classes de evento tipadas em JS; cada evento e so {tipo, ...payload}.
// A UI (ui.js) nunca le o estado "por fora": ela so reage ao que chega aqui.
var TCG = window.TCG || (window.TCG = {});

TCG.EventBus = class EventBus {
  constructor() {
    this._ouvintes = {};
    this.historico = [];
  }

  on(tipo, callback) {
    (this._ouvintes[tipo] ||= []).push(callback);
    return callback;
  }

  off(tipo, callback) {
    const lista = this._ouvintes[tipo];
    if (!lista) return;
    const i = lista.indexOf(callback);
    if (i >= 0) lista.splice(i, 1);
  }

  emit(tipo, payload = {}) {
    const evento = { tipo, ...payload };
    this.historico.push(evento);
    for (const cb of this._ouvintes[tipo] || []) cb(evento);
    // A "pilha de eventos" e o proprio `historico` acima; a cada evento
    // publicado, roda a lista de gatilhos registrados (ver triggers.js) pra
    // ver se algum bate com este tipo de evento.
    if (this.jogo) TCG.dispararTriggers(this.jogo, evento);
  }
};
