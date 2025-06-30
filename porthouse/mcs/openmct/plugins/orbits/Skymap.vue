

<template>
    <div ref="skymap" class="skymap">
        <svg width="150px" height="150px" viewBox="-110 -110 220 220">

            <circle class="grid" cx="0" cy="0" r="90" />
            <circle class="grid" cx="0" cy="0" r="60" />
            <circle class="grid" cx="0" cy="0" r="30" />

            <polyline class="grid" points="-95,0,95,0" />
            <polyline class="grid" points="0,-95,0,95" />

            <text x="0" y="-95" text-anchor="middle" dominant-baseline="auto">N</text>
            <text x="0" y="95" text-anchor="middle" dominant-baseline="hanging">S</text>
            <text x="-95" y="0" text-anchor="end" dominant-baseline="middle">E</text>
            <text x="95" y="0" text-anchor="start" dominant-baseline="middle">W</text>

            <circle class="satellite" cx="65" cy="20" r="3" />
            <circle class="pointing" cx="65" cy="20" r="5" />

        </svg>
    </div>
</template>

<script>
// view-source:https://db-satnogs.freetls.fastly.net/static/js/map.js
export default {
    components: {},
    inject: ['openmct', 'domainObject', 'path'],
    props: [
        options: {
            type: Object,
        },
        renderEngine: {
            type: String,
            default: 'svg',
        }
    ],

    setup(props) {
        console.log(props);
    },
    methods: {


    }
};




</script>

<style scoped>


</style>
