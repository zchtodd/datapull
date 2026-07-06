@echo off
REM Stop and remove the datapull Windows services. RUN AS ADMINISTRATOR.
setlocal
set "NSSM=nssm"
for %%S in (datapull-web datapull-worker datapull-beat) do (
  %NSSM% stop %%S
  %NSSM% remove %%S confirm
)
echo Removed datapull-web, datapull-worker, datapull-beat.
endlocal
