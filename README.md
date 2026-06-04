# Robot autonom care învață să evite obstacolele

Aplicație GUI pentru un robot **Pioneer P3-DX** simulat în **CoppeliaSim**.
Scopul este învățarea prin **Q-learning** pe baza senzorilor de proximitate:
robotul este recompensat când înaintează și primește penalizări mari când se apropie de pereți sau lovește obstacole.

## Cerințe

- **Python** 3.11+
- **CoppeliaSim** instalat
- pachete Python: `customtkinter`, `coppeliasim-zmqremoteapi-client`, `numpy`, `matplotlib`

## Instalare

```bash
pip install customtkinter coppeliasim-zmqremoteapi-client numpy matplotlib
```

## Rulare

```bash
python main.py
```

## Flux de lucru

1. Deschide CoppeliaSim.
2. Pornește o scenă nouă și ține simularea oprită.
3. Desenează sau încarcă labirintul din tab-ul Maze.
4. Apasă Play în CoppeliaSim.
5. Conectează GUI-ul și pornește agentul din tab-ul Train.

## Cum învață robotul

- citește cei 16 senzori de proximitate;
- discretizează starea în zone sigure / apropiate / blocate;
- alege acțiuni cu epsilon-greedy;
- primește recompense pentru mișcare înainte și penalizări pentru coliziuni;
- actualizează Q-table online în timp real.

## Depanare

- **`ModuleNotFoundError: No module named 'customtkinter'`**: instalează pachetul cu `pip`.
- **`ConnectionRefusedError`**: CoppeliaSim nu rulează sau simularea nu e pornită.
- **`RuntimeError: object not found`**: robotul Pioneer P3-DX nu există în scenă.
