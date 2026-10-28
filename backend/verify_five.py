from app.scheduling.flow_shop.simulator import FlowShopSimulator

jobs = ['J1','J2','J3','J4','J5']
processing = {
    'J1':[8,4,4,24,6],
    'J2':[6,2,4,24,2],
    'J3':[10,6,8,22,8],
    'J4':[12,8,6,24,6],
    'J5':[14,4,8,28,8]
}
due_dates = {
    'J1':116,
    'J2':120,
    'J3':114,
    'J4':116,
    'J5':114
}
result = FlowShopSimulator.simulate(jobs, processing, due_dates)
print('Result:', result)
