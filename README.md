# CocBase — подбор баз Clash of Clans

Статический сайт: выбор ратуши (TH6–TH16), цели (фарм / пуш / война), 6 баз со ссылками. Всё в одном `index.html`, данные встроены.

## Деплой на Vercel

1. [Vercel](https://vercel.com) → New Project → Import **abbos-khamidov/coc**.
2. Root Directory оставь пустым (корень репо = сайт). Deploy.
3. В боте в `.env`: `WEBAPP_URL=https://твой-проект.vercel.app`

## Локально

Открой `index.html` в браузере или запусти из папки: `npx serve .` / `python -m http.server 8080`.
