// ---------- Mock data (shape mirrors precos.csv columns from the desktop app) ----------

const PHARMACIES = ["raia", "nissei", "saojoao", "saopaulo", "panvel"];

const PRODUCTS = [
  {
    ean: "7891058109616", nome: "Dipirona Sódica 500mg 10cp", meu: 8.9,
    raia: { v: 9.49, st: "ok" }, nissei: { v: 8.2, st: "ok", min: true }, saojoao: { v: null, st: "nao" }, saopaulo: { v: 8.99, st: "ok" }, panvel: { v: 9.1, st: "ok" },
    obs: "Preço estável nas últimas 3 coletas."
  },
  {
    ean: "7896004703220", nome: "Losartana Potássica 50mg 30cp", meu: 12.4,
    raia: { v: 14.5, st: "ok" }, nissei: { v: 13.2, st: "ok" }, saojoao: { v: 11.8, st: "ok", min: true }, saopaulo: { v: null, st: "indisponivel" }, panvel: { v: 13.99, st: "ok" },
    obs: "São Paulo: fora de estoque desde ontem."
  },
  {
    ean: "7891106004821", nome: "Protetor Solar La Roche Anthelios FPS60 50g", meu: null,
    raia: { v: 89.9, st: "ok" }, nissei: { v: 94.9, st: "ok" }, saojoao: { v: 79.9, st: "ok", min: true }, saopaulo: { v: 92.5, st: "ok" }, panvel: { v: 96.77, st: "ok" },
    obs: "Promoção Droga Raia: de R$ 114,90 por R$ 89,90.", promo: true
  },
  {
    ean: "0070341689684", nome: "Pomada para Tratamento de Assaduras", meu: null,
    raia: { v: null, st: "nao" }, nissei: { v: 111.61, st: "nome" }, saojoao: { v: 24.9, st: "nome", min: true }, saopaulo: { v: null, st: "nao" }, panvel: { v: null, st: "nao" },
    obs: "Droga Raia: busca por nome também falhou.", flag: "conferir"
  },
  {
    ean: "0070341689671", nome: "Neosaldina Analgésico 30 drágeas", meu: 38.5,
    raia: { v: 41.99, st: "nome" }, nissei: { v: 35.81, st: "nome", min: true }, saojoao: { v: 41.72, st: "nome" }, saopaulo: { v: 32.99, st: "divergente" }, panvel: { v: 40.54, st: "nome" },
    obs: "São Paulo: EAN da página não bate com o buscado.", flag: "conferir"
  },
  {
    ean: "7896422500123", nome: "Loratadina 10mg 12cp Genérico", meu: 9.9,
    raia: { v: 10.5, st: "ok" }, nissei: { v: 9.75, st: "ok", min: true }, saojoao: { v: 10.1, st: "ok" }, saopaulo: { v: 10.3, st: "ok" }, panvel: { v: 9.99, st: "ok" },
    obs: "—"
  },
  {
    ean: "7891317012345", nome: "Whey Protein Isolado Baunilha 900g", meu: 189,
    raia: { v: null, st: "nao" }, nissei: { v: null, st: "nao" }, saojoao: { v: 174.9, st: "ok", min: true }, saopaulo: { v: null, st: "nao" }, panvel: { v: 199.9, st: "ok" },
    obs: "Baixa cobertura — item de nicho fitness."
  },
  {
    ean: "7500435154568", nome: "Fralda Pampers Confort Sec M 62un", meu: 54.9,
    raia: { v: 59.9, st: "ok" }, nissei: { v: 57.9, st: "ok" }, saojoao: { v: 52.9, st: "ok", min: true }, saopaulo: { v: 58.5, st: "ok" }, panvel: { v: 56.99, st: "ok" },
    obs: "—"
  },
  {
    ean: "7891024131234", nome: "Shampoo Anticaspa Clear Men 400ml", meu: null,
    raia: { v: 32.9, st: "manual", min: true }, nissei: { v: null, st: "nao" }, saojoao: { v: null, st: "nao" }, saopaulo: { v: null, st: "nao" }, panvel: { v: null, st: "nao" },
    obs: "Preço inserido manualmente por conferência local.", flag: "manual"
  },
  {
    ean: "7896658001122", nome: "Omeprazol 20mg 28cp", meu: 15.2,
    raia: { v: 16.9, st: "ok" }, nissei: { v: 14.5, st: "ok", min: true }, saojoao: { v: 15.99, st: "ok" }, saopaulo: { v: 16.2, st: "ok" }, panvel: { v: 15.75, st: "ok" },
    obs: "—"
  },
  {
    ean: "7891106221456", nome: "Vitamina C Efervescente 1g 10cp", meu: 11.5,
    raia: { v: 12.9, st: "ok" }, nissei: { v: 11.9, st: "ok" }, saojoao: { v: 10.99, st: "ok", min: true }, saopaulo: { v: null, st: "indisponivel" }, panvel: { v: 12.5, st: "ok" },
    obs: "São Paulo: indisponível há 2 dias."
  },
  {
    ean: "7891058345612", nome: "Amoxicilina 500mg Suspensão 150ml", meu: null,
    raia: { v: null, st: "nao" }, nissei: { v: null, st: "nao" }, saojoao: { v: null, st: "nao" }, saopaulo: { v: null, st: "nao" }, panvel: { v: null, st: "nao" },
    obs: "Não encontrado em nenhuma farmácia — checar EAN.", flag: "nao-achou"
  },
  {
    ean: "7896004778901", nome: "Rivotril 2mg 30cp", meu: null,
    raia: { v: null, st: "nao" }, nissei: { v: null, st: "nao" }, saojoao: { v: null, st: "nao" }, saopaulo: { v: null, st: "nao" }, panvel: { v: null, st: "nao" },
    obs: "Controlado — normalmente sem venda online.", flag: "nao-achou"
  },
  {
    ean: "7891350037778", nome: "Sabonete Líquido Protex Cotton 250ml", meu: 8.4,
    raia: { v: 9.29, st: "ok" }, nissei: { v: 8.99, st: "ok" }, saojoao: { v: 7.99, st: "ok", min: true }, saopaulo: { v: 8.79, st: "ok" }, panvel: { v: 9.1, st: "ok" },
    obs: "—"
  },
  {
    ean: "7896511123456", nome: "Termômetro Digital G-Tech", meu: 24.9,
    raia: { v: 27.9, st: "ok" }, nissei: { v: null, st: "indisponivel" }, saojoao: { v: 22.9, st: "ok", min: true }, saopaulo: { v: 26.5, st: "ok" }, panvel: { v: 25.99, st: "ok" },
    obs: "Nissei: fora de estoque."
  },
  {
    ean: "7891268112233", nome: "Multivitamínico Centrum A-Z 60cp", meu: 79.9,
    raia: { v: 89.9, st: "ok" }, nissei: { v: 84.9, st: "ok" }, saojoao: { v: 76.5, st: "ok", min: true }, saopaulo: { v: 88.2, st: "ok" }, panvel: { v: 82.99, st: "ok" },
    obs: "—"
  },
  {
    ean: "7896102233445", nome: "Protetor Auricular de Silicone", meu: null,
    raia: { v: null, st: "nao" }, nissei: { v: 6.9, st: "nome", min: true }, saojoao: { v: null, st: "nao" }, saopaulo: { v: null, st: "nao" }, panvel: { v: null, st: "nao" },
    obs: "Encontrado só por nome alternativo — validar item."
  },
  {
    ean: "7891234321098", nome: "Kit Escova + Creme Dental Colgate Total 12", meu: 18.9,
    raia: { v: 21.9, st: "ok" }, nissei: { v: 19.9, st: "ok" }, saojoao: { v: 18.5, st: "ok", min: true }, saopaulo: { v: 20.4, st: "ok" }, panvel: { v: 19.99, st: "ok" },
    obs: "—"
  }
];

const STATUS_LABEL = {
  ok: "OK", nome: "por nome", divergente: "divergente",
  indisponivel: "indisponível", manual: "manual", nao: "não achou"
};

const money = (v) => v == null ? null : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

function priceCell(entry) {
  if (entry.v == null) {
    return `<span class="price-cell st-nao">${STATUS_LABEL[entry.st]}</span>`;
  }
  const star = entry.min ? `<span class="star">★</span>` : "";
  return `<span class="price-cell st-${entry.st}">${star}${money(entry.v)}</span>`;
}

function rowStatusClasses(p) {
  const classes = new Set();
  const anyMin = PHARMACIES.some(ph => p[ph].min);
  if (anyMin) classes.add("menor-preco");
  if (PHARMACIES.some(ph => p[ph].st === "nome")) classes.add("por-nome");
  if (p.flag === "conferir") classes.add("conferir");
  if (PHARMACIES.every(ph => p[ph].st === "nao")) classes.add("nao-achou");
  if (PHARMACIES.some(ph => p[ph].st === "indisponivel")) classes.add("indisponivel");
  if (PHARMACIES.some(ph => p[ph].st === "manual")) classes.add("manual");
  return [...classes];
}

function dominantStatus(p) {
  if (p.flag === "conferir") return "divergente";
  if (PHARMACIES.some(ph => p[ph].st === "manual")) return "manual";
  if (PHARMACIES.some(ph => p[ph].st === "ok")) return "ok";
  if (PHARMACIES.some(ph => p[ph].st === "nome")) return "nome";
  if (PHARMACIES.every(ph => p[ph].st === "nao")) return "nao";
  return "indisponivel";
}

const tbody = document.getElementById("tableBody");

function renderRows() {
  tbody.innerHTML = PRODUCTS.map((p, i) => {
    const st = dominantStatus(p);
    const filterClasses = rowStatusClasses(p).join(" ");
    return `
    <tr data-index="${i}" data-filters="${filterClasses}" data-search="${(p.ean + " " + p.nome).toLowerCase()}">
      <td class="td-num">${i + 1}</td>
      <td>
        <span class="cell-ean">
          <span class="status-dot st-${st}" title="${STATUS_LABEL[st] || st}"></span>
          ${p.ean}
          <span class="cell-actions">
            <button class="mini-btn" title="Abrir Open Facts">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14L21 3"/></svg>
            </button>
          </span>
        </span>
      </td>
      <td class="cell-product">
        <div class="product-name">${p.nome}</div>
        ${p.promo ? `<div class="product-flags"><span class="flag promo">PROMOÇÃO</span></div>` : ""}
      </td>
      <td>${p.meu != null ? `<span class="mine-price">${money(p.meu)}</span>` : `<span class="mine-empty">sem preço</span>`}</td>
      <td>${priceCell(p.raia)}</td>
      <td>${priceCell(p.nissei)}</td>
      <td>${priceCell(p.saojoao)}</td>
      <td>${priceCell(p.saopaulo)}</td>
      <td>${priceCell(p.panvel)}</td>
      <td class="cell-obs" title="${p.obs}">${p.obs}</td>
    </tr>`;
  }).join("");
}

renderRows();

// ---------- Chip counts (derived from data, not hardcoded) ----------

function updateChipCounts() {
  const all = PRODUCTS.length;
  const counts = { todos: all, "menor-preco": 0, "por-nome": 0, conferir: 0, "nao-achou": 0, indisponivel: 0, manual: 0 };
  PRODUCTS.forEach(p => {
    rowStatusClasses(p).forEach(cls => { if (cls in counts) counts[cls]++; });
  });
  document.querySelectorAll(".count[data-count]").forEach(el => {
    const key = el.dataset.count;
    if (key in counts) el.textContent = counts[key];
  });
}

updateChipCounts();

// ---------- Theme ----------

const themeToggle = document.getElementById("themeToggle");
const iconSun = document.getElementById("iconSun");
const iconMoon = document.getElementById("iconMoon");
const root = document.documentElement;

function applyTheme(mode) {
  if (mode) root.setAttribute("data-theme", mode);
  const isDark = mode === "dark" || (!mode && matchMedia("(prefers-color-scheme: dark)").matches);
  iconSun.style.display = isDark ? "none" : "block";
  iconMoon.style.display = isDark ? "block" : "none";
}

const savedTheme = localStorage.getItem("radar-theme");
if (savedTheme) applyTheme(savedTheme);
else applyTheme();

themeToggle.addEventListener("click", () => {
  const current = root.getAttribute("data-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = current === "dark" ? "light" : "dark";
  localStorage.setItem("radar-theme", next);
  applyTheme(next);
});

// ---------- Run controls ----------

const btnStart = document.getElementById("btnStart");
const btnPause = document.getElementById("btnPause");
const btnStop = document.getElementById("btnStop");
const runState = document.getElementById("runState");
const runDot = document.getElementById("runDot");
const collectDot = document.getElementById("collectDot");
const collectState = document.getElementById("collectState");
const progressFill = document.getElementById("progressFill");

let progress = 86;
requestAnimationFrame(() => { progressFill.style.width = progress + "%"; });

function setRunState(label, dotClass) {
  runState.innerHTML = `<span class="dot ${dotClass}" id="runDot"></span> ${label}`;
}

btnStart.addEventListener("click", () => {
  btnStart.disabled = true;
  btnPause.disabled = false;
  btnStop.disabled = false;
  setRunState("Coletando…", "live");
  collectState.textContent = "Coletando";
  collectDot.className = "dot live";
});

btnPause.addEventListener("click", () => {
  const paused = btnPause.textContent.trim() === "Pausar";
  if (paused) {
    setRunState("Pausado", "warn");
    collectState.textContent = "Pausado";
    collectDot.className = "dot warn";
    btnPause.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg> Retomar`;
  } else {
    setRunState("Coletando…", "live");
    collectState.textContent = "Coletando";
    collectDot.className = "dot live";
    btnPause.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg> Pausar`;
  }
});

btnStop.addEventListener("click", () => {
  btnStart.disabled = false;
  btnPause.disabled = true;
  btnStop.disabled = true;
  btnPause.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg> Pausar`;
  setRunState("Ocioso", "");
  collectState.textContent = "Ocioso";
  collectDot.className = "dot";
});

// ---------- Filters + search ----------

const chipRow = document.getElementById("chipRow");
const searchInput = document.getElementById("searchInput");
const emptyState = document.getElementById("emptyState");
const visibleCount = document.getElementById("visibleCount");

let activeFilter = "todos";

function applyFilters() {
  const term = searchInput.value.trim().toLowerCase();
  let visible = 0;
  tbody.querySelectorAll("tr").forEach(tr => {
    const matchesFilter = activeFilter === "todos" || tr.dataset.filters.split(" ").includes(activeFilter);
    const matchesSearch = !term || tr.dataset.search.includes(term);
    const show = matchesFilter && matchesSearch;
    tr.classList.toggle("row-hidden", !show);
    if (show) visible++;
  });
  visibleCount.textContent = visible;
  emptyState.classList.toggle("show", visible === 0);
}

chipRow.addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  chipRow.querySelectorAll(".chip").forEach(c => c.classList.remove("active"));
  chip.classList.add("active");
  activeFilter = chip.dataset.filter;
  applyFilters();
});

searchInput.addEventListener("input", applyFilters);

// ---------- Sorting ----------

const COLUMN_INDEX = { ean: 1, produto: 2, meu: 3, raia: 4, nissei: 5, saojoao: 6, saopaulo: 7, panvel: 8 };
let sortState = { key: null, dir: 1 };

function cellSortValue(tr, key) {
  const idx = COLUMN_INDEX[key];
  const td = tr.children[idx];
  const text = td.textContent.replace(/[^\d,.-]/g, "").replace(",", ".");
  const num = parseFloat(text);
  if (!isNaN(num) && /[\d]/.test(td.textContent)) return num;
  return td.textContent.trim().toLowerCase();
}

document.querySelectorAll("thead th[data-sort]").forEach(th => {
  th.addEventListener("click", () => {
    const key = th.dataset.sort;
    sortState.dir = sortState.key === key ? -sortState.dir : 1;
    sortState.key = key;
    document.querySelectorAll("thead th").forEach(h => { h.classList.remove("sorted"); h.querySelector(".arrow").textContent = "↕"; });
    th.classList.add("sorted");
    th.querySelector(".arrow").textContent = sortState.dir === 1 ? "↑" : "↓";

    const rows = [...tbody.querySelectorAll("tr")];
    rows.sort((a, b) => {
      const va = cellSortValue(a, key), vb = cellSortValue(b, key);
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * sortState.dir;
      return String(va).localeCompare(String(vb)) * sortState.dir;
    });
    rows.forEach(r => tbody.appendChild(r));
  });
});

// ---------- Log drawer ----------

const logToggle = document.getElementById("logToggle");
const logDrawer = document.getElementById("logDrawer");

logToggle.addEventListener("click", () => {
  const open = logDrawer.classList.toggle("open");
  logToggle.classList.toggle("open", open);
});

// ---------- Pharmacy toggle color swatches respect theme ----------
applyFilters();
