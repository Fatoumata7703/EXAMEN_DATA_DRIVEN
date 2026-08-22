/* Console V4 — script unique, sans dependance externe.
   Toutes les valeurs affichees proviennent de l'API ; rien n'est calcule ici
   en dehors de la mise en forme et du trace de la courbe de prevision. */

"use strict";

const $ = (selecteur) => document.querySelector(selecteur);
const creer = (balise, classe) => {
  const element = document.createElement(balise);
  if (classe) element.className = classe;
  return element;
};

async function appeler(chemin, options) {
  const reponse = await fetch(chemin, options);
  let corps = null;
  try { corps = await reponse.json(); } catch (e) { corps = null; }
  if (!reponse.ok) {
    const detail = corps && corps.detail;
    let texte;
    if (typeof detail === "string") {
      texte = detail;
    } else if (Array.isArray(detail)) {
      texte = detail.map((d) => d.msg || JSON.stringify(d)).join(" ; ");
    } else {
      texte = "erreur " + reponse.status;
    }
    const erreur = new Error(texte);
    erreur.statut = reponse.status;
    throw erreur;
  }
  return corps;
}

const nombre = (valeur, decimales = 2) =>
  Number(valeur).toLocaleString("fr-FR", {
    minimumFractionDigits: decimales, maximumFractionDigits: decimales });

const xof = (valeur) => nombre(valeur, 0) + " XOF";

function messageErreur(conteneur, texte) {
  conteneur.innerHTML = "";
  const bloc = creer("div", "message erreur");
  bloc.textContent = texte;
  conteneur.appendChild(bloc);
}

function etiquetteStatut(statut) {
  const span = creer("span", "etiquette-statut " +
    (statut === "validated_academic" ? "valide" : "exploratoire"));
  span.textContent = statut === "validated_academic" ? "valide (academique)" : "exploratoire";
  return span;
}

/* ------------------------------------------------------------- navigation */

document.querySelectorAll(".onglet").forEach((onglet) => {
  onglet.addEventListener("click", () => {
    document.querySelectorAll(".onglet").forEach((o) => o.classList.remove("actif"));
    document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
    onglet.classList.add("actif");
    $("#page-" + onglet.dataset.page).classList.add("active");
  });
});

/* ------------------------------------------------------------------ etat */

async function chargerEtat() {
  try {
    const sante = await appeler("/health");
    $("#pastille-etat").classList.add("ok");
    const commit = (sante.deployed_commit || "inconnu").slice(0, 7);
    $("#texte-etat").textContent = "Service " + sante.service + " — version " + commit;
  } catch (e) {
    $("#pastille-etat").classList.add("ko");
    $("#texte-etat").textContent = "Service injoignable";
  }
}

/* -------------------------------------------------------- recommandation */

const EXEMPLE_PRICING = "PRD000002";
let produitsRecommandation = [];
const selectionnes = [];

function rafraichirSelection() {
  const zone = $("#reco-selection");
  zone.innerHTML = "";
  selectionnes.forEach((produit, index) => {
    const jeton = creer("span", "jeton");
    jeton.appendChild(document.createTextNode(produit));
    const retirer = creer("button");
    retirer.type = "button";
    retirer.textContent = "x";
    retirer.title = "Retirer " + produit;
    retirer.addEventListener("click", () => {
      selectionnes.splice(index, 1);
      rafraichirSelection();
    });
    jeton.appendChild(retirer);
    zone.appendChild(jeton);
  });
}

$("#reco-ajouter").addEventListener("click", () => {
  const choisi = $("#reco-produits").value;
  if (!choisi) return;
  if (selectionnes.includes(choisi)) {
    messageErreur($("#reco-resultat"),
      "Ce produit est deja dans la liste. Le service refuse les doublons.");
    return;
  }
  selectionnes.push(choisi);
  rafraichirSelection();
});

$("#form-reco").addEventListener("submit", async (evenement) => {
  evenement.preventDefault();
  const conteneur = $("#reco-resultat");
  if (selectionnes.length === 0) {
    messageErreur(conteneur, "Ajoutez au moins un produit candidat.");
    return;
  }
  const bouton = evenement.target.querySelector(".principal");
  bouton.disabled = true;
  conteneur.innerHTML = '<div class="message info">Classement en cours...</div>';

  const corps = { candidate_products: selectionnes };
  const client = $("#reco-client").value.trim();
  if (client) corps.client_id = client;
  const achats = Number($("#reco-achats").value);
  if (!Number.isNaN(achats)) corps.client_purchase_count_before = achats;

  try {
    const donnees = await appeler($("#reco-objectif").value, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corps),
    });
    afficherRecommandation(conteneur, donnees);
  } catch (erreur) {
    messageErreur(conteneur, erreur.message);
  } finally {
    bouton.disabled = false;
  }
});

function afficherRecommandation(conteneur, donnees) {
  conteneur.innerHTML = "";

  if (donnees.fallback_used) {
    const alerte = creer("div", "message erreur");
    alerte.textContent = "Repli automatique : le modele prevu ("
      + donnees.model_requested + ") n'a pas pu servir (" + donnees.fallback_reason
      + "). Le classement provient de " + donnees.model_used + ".";
    conteneur.appendChild(alerte);
  }

  const carte = creer("div", "carte");
  const entete = creer("p");
  entete.innerHTML = "<strong>Modele servi :</strong> " + donnees.model_used
    + " &nbsp;|&nbsp; <strong>Cible :</strong> " + donnees.target;
  carte.appendChild(entete);
  const ligneStatut = creer("p");
  ligneStatut.appendChild(document.createTextNode("Statut du modele servi : "));
  ligneStatut.appendChild(etiquetteStatut(donnees.served_model_status));
  carte.appendChild(ligneStatut);

  const tableau = creer("table");
  tableau.innerHTML = "<thead><tr><th>Rang</th><th>Produit</th>"
    + '<th class="nombre">Score</th></tr></thead>';
  const corps = creer("tbody");
  donnees.results.forEach((ligne) => {
    const tr = creer("tr");
    tr.innerHTML = "<td>" + ligne.rank + "</td><td>" + ligne.product_id
      + '</td><td class="nombre">' + nombre(ligne.score, 4) + "</td>";
    corps.appendChild(tr);
  });
  tableau.appendChild(corps);
  const defilant = creer("div", "tableau-defilant");
  defilant.appendChild(tableau);
  carte.appendChild(defilant);

  if (donnees.dropped_products && donnees.dropped_products.length) {
    const ecartes = creer("p", "note");
    ecartes.textContent = "Produits ecartes car absents du catalogue : "
      + donnees.dropped_products.join(", ");
    carte.appendChild(ecartes);
  }

  const note = creer("p", "note");
  note.textContent = donnees.avertissement;
  carte.appendChild(note);
  conteneur.appendChild(carte);
}

/* ---------------------------------------------------------------- pricing */

$("#pricing-remise").addEventListener("input", (evenement) => {
  $("#pricing-remise-valeur").textContent = evenement.target.value;
});

$("#form-pricing").addEventListener("submit", async (evenement) => {
  evenement.preventDefault();
  const conteneur = $("#pricing-resultat");
  const bouton = evenement.target.querySelector(".principal");
  bouton.disabled = true;
  conteneur.innerHTML = '<div class="message info">Simulation en cours...</div>';
  try {
    const donnees = await appeler("/pricing/simulation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        produit_key: $("#pricing-produit").value,
        discount_proposed: Number($("#pricing-remise").value),
      }),
    });
    afficherPricing(conteneur, donnees);
  } catch (erreur) {
    messageErreur(conteneur, erreur.message);
  } finally {
    bouton.disabled = false;
  }
});

function afficherPricing(conteneur, donnees) {
  conteneur.innerHTML = "";

  // Un volume nul est une prediction reelle, pas un echec : il est affiche
  // comme tel, avec son explication. Un echec de prediction ne passe jamais
  // par ici, il remonte en erreur HTTP explicite.
  if (donnees.volume_nul) {
    const alerte = creer("div", "message alerte");
    alerte.textContent = donnees.message;
    conteneur.appendChild(alerte);
  }

  const mesures = creer("div", "cartes");
  [
    ["Prix catalogue", xof(donnees.prix_catalogue_xof), null],
    ["Prix simule", xof(donnees.prix_simule_xof),
      "remise de " + nombre(donnees.remise_proposee_pct, 0) + " %"],
    ["Cout unitaire", xof(donnees.cout_xof), null],
    ["Marge unitaire", xof(donnees.marge_unitaire_xof), "prix simule moins cout"],
    ["Volume estime 7 j",
      donnees.volume_nul ? "non exploitable" : nombre(donnees.volume_estime_unites_7j, 2) + " unites",
      donnees.volume_nul ? "mediane historique nulle" : "mediane historique par produit"],
    ["Chiffre d'affaires estime",
      donnees.volume_nul ? "non exploitable" : xof(donnees.chiffre_affaires_estime_xof),
      "volume x prix simule"],
    ["Marge estimee",
      donnees.volume_nul ? "non exploitable" : xof(donnees.marge_estimee_xof),
      "volume x marge unitaire"],
  ].forEach(([etiquette, valeur, precision]) => {
    const bloc = creer("div", "mesure" + (valeur === "non exploitable" ? " indisponible" : ""));
    bloc.innerHTML = '<span class="valeur">' + valeur + "</span>"
      + '<span class="etiquette">' + etiquette + "</span>"
      + (precision ? '<span class="precision">' + precision + "</span>" : "");
    mesures.appendChild(bloc);
  });
  conteneur.appendChild(mesures);

  const carte = creer("div", "carte");

  const gardeFous = creer("div", "message "
    + (donnees.garde_fous.prix_sous_cout || donnees.garde_fous.marge_unitaire_negative
       ? "erreur" : "succes"));
  gardeFous.textContent = donnees.garde_fous.marge_unitaire_negative
    ? "Garde-fou declenche : marge unitaire negative."
    : "Garde-fous respectes : prix simule superieur au cout, marge unitaire positive.";
  carte.appendChild(gardeFous);

  const detail = creer("p");
  detail.innerHTML = "<strong>Produit :</strong> " + donnees.produit_key
    + " (" + donnees.categorie + ", classe " + donnees.classe_abc + ")";
  carte.appendChild(detail);

  const ligneModele = creer("p");
  ligneModele.appendChild(document.createTextNode("Modele : " + donnees.modele + " — statut "));
  ligneModele.appendChild(etiquetteStatut(donnees.modele_statut));
  carte.appendChild(ligneModele);

  const note = creer("p", "note");
  note.textContent = donnees.avertissement;
  carte.appendChild(note);
  conteneur.appendChild(carte);
}

/* -------------------------------------------------------------- prevision */

$("#form-prevision").addEventListener("submit", async (evenement) => {
  evenement.preventDefault();
  const conteneur = $("#prevision-resultat");
  const bouton = evenement.target.querySelector(".principal");
  bouton.disabled = true;
  conteneur.innerHTML = '<div class="message info">Chargement de la courbe...</div>';
  try {
    const donnees = await appeler("/forecast/" + encodeURIComponent($("#prevision-produit").value));
    afficherPrevision(conteneur, donnees);
  } catch (erreur) {
    messageErreur(conteneur, erreur.message);
  } finally {
    bouton.disabled = false;
  }
});

function afficherPrevision(conteneur, donnees) {
  conteneur.innerHTML = "";

  const mesures = creer("div", "cartes");
  [
    ["Realise sur 30 jours", nombre(donnees.total_reel_30j, 1) + " unites"],
    ["Prevu sur 30 jours", nombre(donnees.total_prevu_30j, 1) + " unites"],
    ["Ecart absolu", nombre(donnees.ecart_absolu_30j, 1) + " unites"],
  ].forEach(([etiquette, valeur]) => {
    const bloc = creer("div", "mesure");
    bloc.innerHTML = '<span class="valeur">' + valeur
      + '</span><span class="etiquette">' + etiquette + "</span>";
    mesures.appendChild(bloc);
  });
  conteneur.appendChild(mesures);

  const carte = creer("div", "carte");
  const titre = creer("p");
  titre.innerHTML = "<strong>" + donnees.produit_key + "</strong> — " + donnees.nom
    + " &nbsp;|&nbsp; modele : " + donnees.modele
    + " &nbsp;|&nbsp; fenetre debutant le " + donnees.fenetre_debut;
  carte.appendChild(titre);
  carte.appendChild(tracerCourbe(donnees.reel, donnees.prevu, donnees.horizons));

  const legende = creer("div", "legende");
  legende.innerHTML = '<span><i class="trait reel"></i>Realise</span>'
    + '<span><i class="trait prevu"></i>Prevu</span>';
  carte.appendChild(legende);

  const note = creer("p", "note");
  note.textContent = donnees.avertissement;
  carte.appendChild(note);
  conteneur.appendChild(carte);
}

/* Trace un graphique lineaire en SVG, sans bibliotheque externe. */
function tracerCourbe(reel, prevu, horizons) {
  const largeur = 760, hauteur = 280;
  const marge = { haut: 16, droite: 16, bas: 34, gauche: 46 };
  const aireL = largeur - marge.gauche - marge.droite;
  const aireH = hauteur - marge.haut - marge.bas;
  const maxi = Math.max(1, ...reel, ...prevu);

  const x = (i) => marge.gauche + (i / Math.max(1, reel.length - 1)) * aireL;
  const y = (v) => marge.haut + aireH - (v / maxi) * aireH;
  const chemin = (serie) => serie.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1)
    + " " + y(v).toFixed(1)).join(" ");

  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", "0 0 " + largeur + " " + hauteur);
  svg.setAttribute("class", "graphique");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label",
    "Courbe du realise et du prevu sur " + reel.length + " jours");

  // grille horizontale et graduations
  for (let n = 0; n <= 4; n += 1) {
    const valeur = (maxi / 4) * n;
    const yy = y(valeur);
    const ligne = document.createElementNS(svgNS, "line");
    ligne.setAttribute("x1", marge.gauche); ligne.setAttribute("x2", largeur - marge.droite);
    ligne.setAttribute("y1", yy); ligne.setAttribute("y2", yy);
    ligne.setAttribute("class", n === 0 ? "axe" : "grille");
    svg.appendChild(ligne);
    const texte = document.createElementNS(svgNS, "text");
    texte.setAttribute("x", marge.gauche - 8);
    texte.setAttribute("y", yy + 3);
    texte.setAttribute("text-anchor", "end");
    texte.textContent = nombre(valeur, 0);
    svg.appendChild(texte);
  }

  // graduations horizontales
  [0, Math.floor(reel.length / 2), reel.length - 1].forEach((i) => {
    const texte = document.createElementNS(svgNS, "text");
    texte.setAttribute("x", x(i));
    texte.setAttribute("y", hauteur - marge.bas + 18);
    texte.setAttribute("text-anchor", "middle");
    texte.textContent = "J+" + horizons[i];
    svg.appendChild(texte);
  });

  [["ligne-reel", reel], ["ligne-prevu", prevu]].forEach(([classe, serie]) => {
    const trace = document.createElementNS(svgNS, "path");
    trace.setAttribute("d", chemin(serie));
    trace.setAttribute("class", classe);
    svg.appendChild(trace);
  });

  return svg;
}

/* ---------------------------------------------------------------- modeles */

function badge(texte, classe) {
  const span = creer("span", "etiquette-statut " + classe);
  span.textContent = texte;
  return span;
}

function badgeStatut(statut) {
  if (statut === "validated_academic") return badge("valide (academique)", "valide");
  if (statut === "exploratory") return badge("exploratoire", "exploratoire");
  if (statut === "validated") return badge("reference validee", "reference");
  if (statut === "simulation_only") return badge("simulation uniquement", "simulation");
  return badge(statut || "indisponible", "indisponible");
}

/* Valeur numerique, ou mention explicite si la metrique n'existe pas.
   Ne substitue jamais un zero a une valeur absente. */
function valeurOuIndisponible(valeur, decimales) {
  return (valeur === null || valeur === undefined)
    ? "non disponible" : nombre(valeur, decimales);
}

function pourcentage(valeur) {
  return (valeur === null || valeur === undefined)
    ? "non disponible" : (valeur >= 0 ? "+" : "") + nombre(valeur * 100, 2) + " %";
}

function bloc(titre) {
  const section = creer("div", "domaine");
  const h3 = creer("h3");
  h3.textContent = titre;
  section.appendChild(h3);
  return section;
}

function tableauDe(entetes, lignes) {
  const table = creer("table");
  table.innerHTML = "<thead><tr>" + entetes.map((e) => "<th>" + e + "</th>").join("") + "</tr></thead>";
  const corps = creer("tbody");
  lignes.forEach((cellules) => {
    const tr = creer("tr");
    cellules.forEach((cellule) => {
      const td = creer("td");
      if (cellule instanceof Node) td.appendChild(cellule);
      else td.textContent = cellule;
      tr.appendChild(td);
    });
    corps.appendChild(tr);
  });
  table.appendChild(corps);
  const defilant = creer("div", "tableau-defilant");
  defilant.appendChild(table);
  return defilant;
}

function limite(texte) {
  const p = creer("p", "limite");
  p.textContent = texte;
  return p;
}

async function chargerModeles() {
  const conteneur = $("#modeles-resultat");
  try {
    const scores = await appeler("/metrics");
    const meta = await appeler("/metadata");
    conteneur.innerHTML = "";

    const entete = creer("div", "carte");
    entete.innerHTML = "<p><strong>Service :</strong> " + meta.service
      + " &nbsp;|&nbsp; <strong>Version deployee :</strong> "
      + (meta.deployed_commit || "inconnue")
      + "</p><p><strong>Statut des donnees :</strong> " + scores.statut_donnees + "</p>";
    conteneur.appendChild(entete);

    /* ---------------------------------------------------------- forecasting */
    const f = scores.forecasting;
    const carteF = creer("div", "carte");
    const sectionF = bloc("Forecasting");
    sectionF.appendChild(tableauDe(
      ["Element", "Valeur"],
      [
        ["Modele de planification 30 jours", f.planning_model || "non disponible"],
        ["Modele quotidien", f.daily_model || "non disponible"],
        ["WAPE30 macro", valeurOuIndisponible(f.wape30_macro, 5)],
        ["WAPE30 micro", valeurOuIndisponible(f.wape30_micro, 5)],
        ["Forecast Bias macro", valeurOuIndisponible(f.forecast_bias_macro, 5)],
        ["Statut", badgeStatut(f.status)],
        ["Usage", f.usage || "non disponible"],
      ]));
    sectionF.appendChild(limite(
      "Limite : une WAPE30 de " + valeurOuIndisponible(f.wape30_macro, 5)
      + " ne signifie pas une exactitude de 90 pour cent. La demande est fortement "
      + "intermittente : de nombreux produits ne se vendent pas chaque jour, ce qui "
      + "gonfle mecaniquement l'erreur relative. Modele repris en lecture seule, "
      + "jamais reentraine par ce service."));
    carteF.appendChild(sectionF);
    conteneur.appendChild(carteF);

    /* -------------------------------------------------------------- pricing */
    const pr = scores.pricing;
    const carteP = creer("div", "carte");
    const sectionP = bloc("Pricing");
    const enteteP = creer("p");
    enteteP.appendChild(document.createTextNode("Modele : " + (pr.model || "non disponible") + " — "));
    enteteP.appendChild(badgeStatut(pr.status));
    sectionP.appendChild(enteteP);

    const lignesP = Object.keys(pr.targets).map((cible) => {
      const c = pr.targets[cible];
      return [cible, valeurOuIndisponible(c.wape_macro, 4),
              valeurOuIndisponible(c.bias_macro, 4), badgeStatut(c.status)];
    });
    sectionP.appendChild(tableauDe(["Cible", "WAPE macro", "Biais macro", "Statut"], lignesP));
    sectionP.appendChild(limite(
      "Limites : aucun effet causal n'est estime (causal_effect_estimated = "
      + pr.causal_effect_estimated + ") et aucun prix optimal n'est calcule "
      + "automatiquement (automatic_optimal_price = " + pr.automatic_optimal_price + "). "
      + "Aucun modele d'apprentissage n'a battu la mediane par produit : la baseline "
      + "reste la reference. Usage autorise : simulation academique uniquement."));
    carteP.appendChild(sectionP);
    conteneur.appendChild(carteP);

    /* ------------------------------------------------------- recommandation */
    const r = scores.recommendation;
    const carteR = creer("div", "carte");
    const sectionR = bloc("Recommandation");
    const roles = { purchase: "Achat", add_to_cart: "Ajout au panier", view: "Consultation" };
    const lignesR = Object.keys(roles).map((role) => {
      const e = r[role] || {};
      return [roles[role], e.target || "non disponible", e.model || "non disponible",
              pourcentage(e.ndcg10_gain_relative),
              valeurOuIndisponible(e.holm_pvalue_independent, 5),
              badgeStatut(e.status),
              e.used_by_default === true ? "oui" : (e.used_by_default === false ? "non" : "-"),
              e.fallback || "-"];
    });
    sectionR.appendChild(tableauDe(
      ["Role", "Cible", "Modele", "Gain NDCG@10", "p Holm independante",
       "Statut", "Par defaut", "Repli"], lignesR));
    sectionR.appendChild(limite(
      "Limites : gains mesures hors ligne sur des slates fermees de 5 candidats ; "
      + "Recall@k y est invariant au reclassement, seul NDCG@10 discrimine. Le modele "
      + "de consultation reste exploratoire : son gain n'est pas significatif apres "
      + "correction, il n'est donc jamais servi par defaut. Repli general : "
      + "popularite_globale_v1."));
    carteR.appendChild(sectionR);
    conteneur.appendChild(carteR);
  } catch (erreur) {
    messageErreur(conteneur, erreur.message);
  }
}

/* --------------------------------------------------------- initialisation */

function remplirListe(select, valeurs, formatter) {
  select.innerHTML = "";
  valeurs.forEach((valeur) => {
    const option = creer("option");
    option.value = typeof valeur === "string" ? valeur : valeur.produit_key;
    option.textContent = formatter ? formatter(valeur) : valeur;
    select.appendChild(option);
  });
}

async function chargerCatalogues() {
  try {
    const pricing = await appeler("/catalogue");
    produitsRecommandation = pricing.recommandation;
    remplirListe($("#reco-produits"), produitsRecommandation);
    remplirListe($("#pricing-produit"), pricing.pricing);
    // Exemple connu a volume non nul, pour que la page ne s'ouvre pas sur
    // un produit a rotation lente dont toutes les valeurs valent zero.
    if (pricing.pricing.includes(EXEMPLE_PRICING)) {
      $("#pricing-produit").value = EXEMPLE_PRICING;
    }
  } catch (erreur) {
    $("#reco-produits").innerHTML = "<option>catalogue indisponible</option>";
    $("#pricing-produit").innerHTML = "<option>catalogue indisponible</option>";
  }
}

async function chargerPrevision() {
  try {
    const synthese = await appeler("/forecast");
    const cartes = $("#prevision-synthese");
    cartes.innerHTML = "";
    [
      ["Modele 30 jours", synthese.modele_planification_30j],
      ["Modele quotidien", synthese.modele_quotidien],
      ["WAPE30 macro", nombre(synthese.metriques.wape30_macro, 5)],
      ["WAPE30 micro", nombre(synthese.metriques.wape30_micro, 5)],
      ["Biais macro", nombre(synthese.metriques.forecast_bias_macro, 5)],
    ].forEach(([etiquette, valeur]) => {
      const bloc = creer("div", "mesure");
      bloc.innerHTML = '<span class="valeur">' + valeur
        + '</span><span class="etiquette">' + etiquette + "</span>";
      cartes.appendChild(bloc);
    });

    const liste = await appeler("/forecast/produits");
    remplirListe($("#prevision-produit"), liste.produits,
      (p) => p.produit_key + " — " + p.nom);
  } catch (erreur) {
    $("#prevision-produit").innerHTML = "<option>prevision indisponible</option>";
    $("#prevision-synthese").innerHTML =
      '<div class="message erreur">Prevision indisponible : ' + erreur.message + "</div>";
  }
}

chargerEtat();
chargerCatalogues();
chargerPrevision();
chargerModeles();
rafraichirSelection();
