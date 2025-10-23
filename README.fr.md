[English](./README.md) | [简体中文](./README.zh-CN.md) | [Français](./README.fr.md)

---

# T4T - Task For Task

**T4T est une plateforme d'automatisation de bureau hautement extensible construite avec Python et PyQt5. Elle est conçue pour être un hub flexible et événementiel pour la gestion et l'exécution des tâches.**

[![Licence: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ Fonctionnalités Clés

*   **Déclencheurs Bi-mode**: Prend en charge à la fois les tâches **planifiées** traditionnelles (Cron, Intervalle) et les tâches puissantes **pilotées par événements**.
*   **Système de Modules Enfichables**: Créez de nouveaux modules fonctionnels avec un simple `manifest.yaml` et un script Python, permettant un véritable "hot-plugging".
*   **Intégration de Message Bus**: Un client MQTT intégré permet une communication découplée entre les tâches et avec des systèmes externes (par ex., appareils IoT, API Web).
*   **Exécution Concurrente**: Utilise un `ThreadPoolExecutor` pour exécuter toutes les tâches de manière asynchrone, garantissant une interface utilisateur fluide et une exécution non bloquante des tâches.
*   **Interface Utilisateur Riche**: Fournit des fonctionnalités pour la gestion des tâches, la journalisation en temps réel, la surveillance de l'état, le support multilingue et le changement de thème.
*   **Journalisation Contextuelle**: Les journaux de chaque tâche sont automatiquement associés à l'instance de la tâche pour un débogage clair et facile.

## 📂 Structure du Projet
```
/
├─── core/              # Logique applicative principale (TaskManager, ModuleManager, etc.)
├─── docs/              # Fichiers de documentation
├─── i18n/              # Fichiers d'internationalisation (en.json, zh-CN.json, fr.json)
├─── modules/           # Modèles de modules réutilisables (manifest.yaml, scripts)
├─── tasks/             # Instances de tâches configurées par l'utilisateur
├─── utils/             # Classes utilitaires (Logger, ThemeManager, MessageBus)
├─── view/              # Composants et fenêtres de l'interface utilisateur PyQt5
├─── main.py            # Point d'entrée principal de l'application
├─── requirements.txt   # Dépendances Python
└─── README.md          # Ce fichier
```

## 🏛️ Architecture du Projet

Le projet suit une architecture en couches, séparant clairement la présentation, la logique métier et les services.

*   **Vue (`view/`)**: L'interface utilisateur complète, construite avec PyQt5. Elle est responsable de l'affichage des données et de la transmission des actions de l'utilisateur à la couche principale.
*   **Noyau (`core/`)**: Le cœur de l'application. Il contient la logique métier principale :
    *   `ModuleManager`: Découvre et gère tous les modules disponibles (`modules/`).
    *   `TaskManager`: Gère le cycle de vie de toutes les instances de tâches (`tasks/`), y compris leur création, exécution et état.
    *   `Scheduler`: Une façade pour `APScheduler` qui gère tous les déclencheurs basés sur le temps.
    *   `StateManager`: Gère l'état de l'application et des tâches.
*   **Utilitaires (`utils/`)**: Une collection de classes et de fonctions utilitaires utilisées dans toute l'application, telles que la journalisation, l'i18n, la gestion des thèmes et le bus de messages à l'échelle du système.
*   **Modules & Tâches**:
    *   `modules/`: Contient les "modèles" de tâches réutilisables.
    *   `tasks/`: Contient les instances configurées des modules, chacune avec son propre `config.yaml`.

## 🚀 Stack Technique

*   **Backend**: Python 3
*   **UI**: PyQt5
*   **Automatisation du bureau**: PyAutoGUI
*   **Architecture de base**: Événementielle, Publication/Abonnement
*   **Concurrence**: `ThreadPoolExecutor`
*   **File d'attente de messages**: Paho-MQTT
*   **Planification**: APScheduler (pour les tâches de type `schedule`)

## 📖 Documentation

*   **[Manuel de l'utilisateur](./docs/user_manual.md)**: Un guide pour les utilisateurs finaux sur la façon d'utiliser le logiciel.
*   **[Guide de développement](./docs/development_guide.md)**: Un guide détaillé pour les développeurs sur la façon de créer de nouveaux modules V2, expliquant l'API principale et l'architecture.

## Démarrage Rapide

1.  **Clonez le dépôt**
    ```bash
    git clone https://github.com/your-repo/T4T.git
    cd T4T
    ```

2.  **Installez les dépendances**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Exécutez l'application**
    ```bash
    python main.py
    ```

## Contribuer

Les contributions de toute nature sont les bienvenues ! Qu'il s'agisse de rapports de bogues, de suggestions de fonctionnalités ou de pull requests.

1.  Forkez le projet
2.  Créez votre branche de fonctionnalité (`git checkout -b feature/AmazingFeature`)
3.  Commitez vos modifications (`git commit -m 'Add some AmazingFeature'`)
4.  Poussez vers la branche (`git push origin feature/AmazingFeature`)
5.  Ouvrez une Pull Request

---

## 📄 Licence

Ce projet est sous licence [MIT](LICENSE).
