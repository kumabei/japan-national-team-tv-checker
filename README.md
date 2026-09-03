# サッカー日本代表 TV放送チェッカー

日本代表戦（親善試合・キリンカップ・アジア予選・W杯本大会など）のTV放送予定を
Goal.comから自動取得し、ブラウザ・iPhoneホーム画面で確認できるアプリです。

W杯2026 TV放送チェッカー（`kumabei/worldcup-checker`）のデータを初期値として
引き継いでいます。W杯本大会に限らず、今後も日本代表戦がある限り使い続ける想定です。

## ファイル構成

- `scraper.py` — Goal.comをスクレイピングして matches.json を更新する
- `matches.json` — 試合データ
- `index.html` — 表示画面（ホーム画面に追加してアプリ風に使える）
- `icon.png` / `generate_icon.py` — ホーム画面アイコン

## scraper.py の実行方法

```bash
pip install requests beautifulsoup4
python scraper.py
```

新しく放送予定が確定した試合があれば、コンソールに一覧が出力されます。

## テストの実行方法

```bash
pip install pytest
python -m pytest tests/test_scraper.py -v
```

## icon.png の再生成方法

```bash
pip install Pillow
python generate_icon.py
```
